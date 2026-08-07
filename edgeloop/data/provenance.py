"""Provenance and the missing-field register.

Two non-negotiables live in this file.

**Missing data is null and logged, never inferred** (constraint 5). Anything the
source did not return goes into ``Provenance.missing`` and rides all the way to
the UI. There is no interpolation, no last-good-value carry-forward, no
"reasonable estimate". A caller that wants a number that is not there gets
``None`` and a named entry explaining which field, from which endpoint, was
absent.

**Point-in-time discipline** (constraint 6). Every record carries two distinct
timestamps and conflating them is the bug this whole class exists to prevent:

``fetched_at``
    When *we* called. Wall clock. Useless for backtesting.

``data_asof``
    When the data was *true*. For a quote, the exchange timestamp. For a
    fundamental, the SEC acceptance timestamp -- NOT the fiscal period end.
    NVDA's FY2026 income statement has ``date`` 2026-01-25 and ``acceptedDate``
    2026-02-25. Using the former would let a backtest trade on a filing a month
    before it existed. That is exactly the leak this system is built to not
    have.

Nothing here backtests yet. The discipline is installed now because retrofitting
it later means throwing away every row written in the meantime.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Quality(str, Enum):
    """How much weight a consumer may put on this record."""

    OK = "ok"
    # Served from disk cache past its TTL because a refetch was not permitted
    # (rate governor said no). Usable, but the age is real and is reported.
    STALE = "stale"
    # The call succeeded but one or more expected fields were absent.
    PARTIAL = "partial"
    # The call did not produce usable data at all.
    MISSING = "missing"


@dataclass(frozen=True)
class MissingField:
    """One field the source did not return.

    ``path`` is dotted within the response row, e.g. "beta" or "0.acceptedDate".
    ``reason`` says what happened, in words a user can read.
    """

    endpoint: str
    path: str
    reason: str

    def __str__(self) -> str:
        return f"{self.endpoint}.{self.path}: {self.reason}"


@dataclass
class Provenance:
    """Where one piece of data came from and how much to trust it."""

    source: str                    # "fmp"
    endpoint: str                  # registry key, e.g. "historical_price_light"
    params: dict[str, Any]
    fetched_at: datetime
    data_asof: datetime | None     # None only when the source published no timestamp
    quality: Quality = Quality.OK
    cache_hit: bool = False
    missing: list[MissingField] = field(default_factory=list)
    note: str = ""

    def __post_init__(self) -> None:
        if self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at must be timezone-aware")
        if self.data_asof is not None and self.data_asof.tzinfo is None:
            raise ValueError("data_asof must be timezone-aware")
        # A record whose data postdates the fetch is incoherent -- either a
        # clock problem or a parsing bug. Refuse it here rather than let it
        # reach the no-lookahead database constraint and abort a transaction.
        if self.data_asof is not None and self.data_asof > self.fetched_at:
            raise ValueError(
                f"data_asof {self.data_asof.isoformat()} is after fetched_at "
                f"{self.fetched_at.isoformat()} for {self.endpoint}; refusing to "
                "create a record that claims to know the future"
            )

    def add_missing(self, path: str, reason: str) -> None:
        self.missing.append(MissingField(self.endpoint, path, reason))
        if self.quality is Quality.OK:
            self.quality = Quality.PARTIAL

    @property
    def age_seconds(self) -> float | None:
        if self.data_asof is None:
            return None
        return (self.fetched_at - self.data_asof).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "endpoint": self.endpoint,
            "params": self.params,
            "fetched_at": self.fetched_at.isoformat(),
            "data_asof": self.data_asof.isoformat() if self.data_asof else None,
            "quality": self.quality.value,
            "cache_hit": self.cache_hit,
            "missing": [str(m) for m in self.missing],
            "age_seconds": self.age_seconds,
            "note": self.note,
        }

    def render(self) -> str:
        """Human-readable one-block provenance record.

        This is what phase 1 prints to prove the pipeline end to end.
        """
        lines = [
            f"  source      : {self.source}",
            f"  endpoint    : {self.endpoint}",
            f"  params      : {json.dumps(self.params, sort_keys=True)}",
            f"  fetched_at  : {self.fetched_at.isoformat()}",
            f"  data_asof   : {self.data_asof.isoformat() if self.data_asof else 'NULL (source published no timestamp)'}",
            f"  quality     : {self.quality.value}",
            f"  cache_hit   : {self.cache_hit}",
        ]
        if self.age_seconds is not None:
            lines.append(f"  data age    : {self.age_seconds / 3600:.2f}h at fetch time")
        if self.missing:
            lines.append(f"  missing[{len(self.missing)}] :")
            lines.extend(f"      - {m}" for m in self.missing)
        else:
            lines.append("  missing[0]  : (none)")
        if self.note:
            lines.append(f"  note        : {self.note}")
        return "\n".join(lines)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def input_hash(payload: Any) -> str:
    """Stable content hash over arbitrary JSON-able input.

    Backs ``forecasts.input_hash``. The contract is that hashing the price
    series plus every parameter lets any forecast be regenerated exactly, so
    this must be insensitive to dict ordering and stable across processes
    (Python's built-in hash() is neither).
    """
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
