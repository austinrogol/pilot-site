"""Rate governor for FMP calls.

Ported from the cadence limiter in desk-trading
(``research/llm_experiment/rate_governor.py``). That one caps LLM generation
cycles; this one caps HTTP calls to a metered vendor. The mechanism is the same
and so are the three design choices, all of which were made in the conservative
direction and are kept here deliberately:

* **Trailing 24-hour window, not calendar day.** A midnight reset permits a
  burst of twice the cap across a few hours (cap at 23:00, cap again at 00:30),
  and "day" is ambiguous between a Railway container on UTC and the operator.
  A trailing window has no seam to burst through.

* **Fail closed.** An unreadable state file, a naive datetime, an unparseable
  history entry, or a future-dated timestamp blocks the call with a structured
  reason. Nothing ambiguous resolves toward "permitted". An unreadable ledger
  could be hiding real calls.

* **Durable, isolated state.** Call records append to a local JSON file written
  atomically, so the cap survives a process restart. It is not the ledger and
  touches no main-line storage.

What differs from desk-trading: the budget here is per-call rather than
per-cycle, and there is a minimum spacing in *seconds* rather than hours,
because the thing being protected is a request-per-day quota rather than a
human-scale spend.

The governor only decides permission. It performs no I/O to FMP and knows
nothing about what the call is for.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path

_TRAILING_WINDOW = dt.timedelta(hours=24)


@dataclass(frozen=True)
class Decision:
    """The answer, plus enough detail for a caller to know what to do next.

    Two kinds of "no" are distinguished, because they call for opposite
    responses:

    ``hard_block=True``
        The daily cap is spent, or the state is unreadable. Waiting will not
        help on any useful timescale. The caller must stop.

    ``hard_block=False``
        Only the minimum-spacing throttle is in the way. ``retry_after_seconds``
        says how long until the call is permitted -- a fraction of a second.
        The caller should sleep and proceed. Refusing here would turn a
        politeness throttle into a budget, which is not what it is for.
    """

    permitted: bool
    reason: str
    calls_in_window: int
    limit: int
    hard_block: bool = True
    retry_after_seconds: float | None = None

    def __bool__(self) -> bool:
        return self.permitted


class GovernorStateError(RuntimeError):
    """The durable state is unreadable and the governor refuses to guess."""


def _parse_ts(raw: object) -> dt.datetime | None:
    """ISO-8601 -> aware datetime, or None if unparseable or naive.

    A naive timestamp counts as unparseable: the governor will not guess which
    timezone a recorded call happened in.
    """
    if not isinstance(raw, str):
        return None
    try:
        ts = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    return ts if ts.tzinfo is not None else None


class RateGovernor:
    def __init__(
        self,
        state_path: Path,
        max_calls_per_day: int,
        min_seconds_between_calls: float = 0.25,
    ):
        if max_calls_per_day < 1:
            raise ValueError("max_calls_per_day must be >= 1")
        self.state_path = Path(state_path)
        self.max_calls_per_day = max_calls_per_day
        self.min_seconds_between_calls = min_seconds_between_calls

    # -- durable state ------------------------------------------------------

    def load_history(self) -> list[str] | None:
        """Read the call ledger.

        Missing/empty -> [] (a fresh deploy starts permitted).
        Corrupt or wrong-shaped -> None, which callers MUST treat as blocked.
        """
        if not self.state_path.exists():
            return []
        try:
            text = self.state_path.read_text()
        except OSError:
            return None
        if not text.strip():
            return []
        try:
            state = json.loads(text)
        except json.JSONDecodeError:
            return None
        calls = state.get("calls") if isinstance(state, dict) else None
        if not isinstance(calls, list) or not all(isinstance(c, str) for c in calls):
            return None
        return calls

    def _write_history(self, history: list[str]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_name(self.state_path.name + ".tmp")
        tmp.write_text(json.dumps({"calls": history}, indent=2) + "\n")
        os.replace(tmp, self.state_path)

    # -- the decision -------------------------------------------------------

    def evaluate(self, now: dt.datetime, history: list[str] | None) -> Decision:
        """Pure function: is one more call permitted right now?

        Reports every limit that blocks, not just the first, so an operator
        reading the reason does not have to fix them one at a time.
        """
        if not isinstance(now, dt.datetime) or now.tzinfo is None:
            return Decision(
                False,
                "blocked: 'now' must be a timezone-aware datetime; the governor "
                "refuses to reason about a call budget with an ambiguous clock",
                0,
                self.max_calls_per_day,
            )
        if history is None:
            return Decision(
                False,
                f"blocked: governor state at {self.state_path} is unreadable or "
                "corrupt; an unreadable ledger could be hiding real calls, so the "
                "governor fails closed -- inspect and repair the file by hand",
                0,
                self.max_calls_per_day,
            )

        parsed: list[dt.datetime] = []
        for index, raw in enumerate(history):
            ts = _parse_ts(raw)
            if ts is None:
                return Decision(
                    False,
                    f"blocked: governor history entry [{index}] is unparseable or "
                    f"naive ({raw!r}); an unreadable record could be hiding a real "
                    "call, so the governor fails closed",
                    0,
                    self.max_calls_per_day,
                )
            parsed.append(ts)

        in_window = [t for t in parsed if t > now - _TRAILING_WINDOW]
        hard_reasons: list[str] = []
        soft_reasons: list[str] = []
        retry_after: float | None = None

        if len(in_window) >= self.max_calls_per_day:
            ordered = sorted(in_window)
            frees_at = ordered[len(ordered) - self.max_calls_per_day] + _TRAILING_WINDOW
            hard_reasons.append(
                f"daily cap: {len(in_window)} call(s) in the trailing 24h >= "
                f"max_calls_per_day={self.max_calls_per_day}; next permitted after "
                f"{frees_at.isoformat()}"
            )

        if parsed:
            last = max(parsed)
            spacing = dt.timedelta(seconds=self.min_seconds_between_calls)
            if now - last < spacing:
                retry_after = (last + spacing - now).total_seconds()
                soft_reasons.append(
                    f"too soon: last call at {last.isoformat()}, minimum spacing is "
                    f"{self.min_seconds_between_calls}s; next permitted after "
                    f"{(last + spacing).isoformat()}"
                )

        future = [t for t in parsed if t > now]
        if future:
            # Clock skew or a corrupted entry. Always hard: we cannot tell how
            # far ahead the clock is, so sleeping is not a bounded wait.
            hard_reasons.append(
                f"{len(future)} recorded call(s) are in the FUTURE of 'now' (clock "
                "skew or a corrupted entry); they count against both limits and are "
                "never ignored"
            )

        if hard_reasons or soft_reasons:
            return Decision(
                permitted=False,
                reason="blocked: " + "; ".join(hard_reasons + soft_reasons),
                calls_in_window=len(in_window),
                limit=self.max_calls_per_day,
                hard_block=bool(hard_reasons),
                retry_after_seconds=None if hard_reasons else retry_after,
            )
        return Decision(
            permitted=True,
            reason=(
                f"permitted: {len(in_window)} of max_calls_per_day="
                f"{self.max_calls_per_day} call(s) in the trailing 24h, spacing clear"
            ),
            calls_in_window=len(in_window),
            limit=self.max_calls_per_day,
            hard_block=False,
        )

    def record(self, now: dt.datetime) -> list[str]:
        """Append one call timestamp. Refuses to touch already-corrupt state."""
        if not isinstance(now, dt.datetime) or now.tzinfo is None:
            raise ValueError("record requires a timezone-aware datetime")
        history = self.load_history()
        if history is None:
            raise GovernorStateError(
                f"refusing to overwrite corrupt governor state at {self.state_path}; "
                "overwriting would erase the very history the cap rides on -- "
                "inspect and repair it by hand"
            )
        history = history + [now.astimezone(dt.timezone.utc).isoformat()]
        self._write_history(history)
        return history

    def check_and_record(self, now: dt.datetime) -> Decision:
        """The single entry point. Check and, if permitted, record atomically
        enough that a call cannot slip between the check and its recording.

        A blocked check records nothing.
        """
        decision = self.evaluate(now, self.load_history())
        if decision.permitted:
            self.record(now)
        return decision

    # -- introspection ------------------------------------------------------

    def budget(self, now: dt.datetime) -> dict[str, object]:
        history = self.load_history()
        if history is None:
            return {"readable": False, "used": None, "limit": self.max_calls_per_day}
        parsed = [t for t in (_parse_ts(r) for r in history) if t is not None]
        used = len([t for t in parsed if t > now - _TRAILING_WINDOW])
        return {
            "readable": True,
            "used": used,
            "limit": self.max_calls_per_day,
            "remaining": max(0, self.max_calls_per_day - used),
        }
