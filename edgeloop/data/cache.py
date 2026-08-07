"""Disk cache keyed on (endpoint, params, date).

The free FMP tier allows a few hundred calls a day and a single ticker analysis
is budgeted at under 8 uncached calls, so the cache is not an optimisation --
it is what makes the budget hold. It is also what makes a run reproducible: a
cached body is the exact bytes the model saw.

Keying includes the UTC date, per the spec. That gives a natural daily rollover
for EOD data without any invalidation logic, and it means yesterday's response
stays on disk as a record of what was true yesterday rather than being
overwritten. Entries additionally carry a TTL so intraday-ish endpoints (quote)
can expire sooner than the date boundary.

Entries are never silently deleted. `purge()` exists but must be called
explicitly.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .provenance import input_hash


@dataclass(frozen=True)
class CacheEntry:
    key: str
    endpoint: str
    params: dict[str, Any]
    body: Any
    stored_at: datetime
    ttl_seconds: int

    def age_seconds(self, now: datetime) -> float:
        return (now - self.stored_at).total_seconds()

    def expired(self, now: datetime) -> bool:
        return self.age_seconds(now) > self.ttl_seconds


class DiskCache:
    def __init__(self, root: Path):
        self.root = Path(root)

    # -- key construction ---------------------------------------------------

    @staticmethod
    def build_key(endpoint: str, params: dict[str, Any], on_date: str) -> str:
        """(endpoint, params, date) -> stable key.

        The api key is never part of params by the time it reaches here (the
        client injects it at the transport boundary), so it can never leak into
        a filename.
        """
        digest = input_hash({"endpoint": endpoint, "params": params, "date": on_date})
        return f"{endpoint}/{on_date}/{digest[:32]}"

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    # -- read / write -------------------------------------------------------

    def get(self, key: str) -> CacheEntry | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            # A corrupt entry is treated as a miss, not as an error. Unlike the
            # rate governor -- where an unreadable ledger could hide real calls
            # and so must fail closed -- a corrupt cache entry can only cost one
            # refetch, and refetching is the safe direction.
            return None
        try:
            return CacheEntry(
                key=key,
                endpoint=raw["endpoint"],
                params=raw["params"],
                body=raw["body"],
                stored_at=datetime.fromisoformat(raw["stored_at"]),
                ttl_seconds=int(raw["ttl_seconds"]),
            )
        except (KeyError, ValueError, TypeError):
            return None

    def put(
        self,
        key: str,
        endpoint: str,
        params: dict[str, Any],
        body: Any,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> CacheEntry:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("cache timestamps must be timezone-aware")
        entry = CacheEntry(
            key=key,
            endpoint=endpoint,
            params=params,
            body=body,
            stored_at=now,
            ttl_seconds=ttl_seconds,
        )
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "endpoint": endpoint,
            "params": params,
            "stored_at": now.isoformat(),
            "ttl_seconds": ttl_seconds,
            "body": body,
        }
        # Atomic: a crash mid-write must not leave a half-written body that
        # parses as valid JSON.
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(payload, handle)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return entry

    # -- introspection ------------------------------------------------------

    def stats(self) -> dict[str, int]:
        if not self.root.exists():
            return {"entries": 0, "bytes": 0}
        entries = list(self.root.rglob("*.json"))
        return {
            "entries": len(entries),
            "bytes": sum(p.stat().st_size for p in entries),
        }

    def purge(self, endpoint: str | None = None) -> int:
        """Delete cached bodies. Explicit call only; nothing purges on its own."""
        target = self.root / endpoint if endpoint else self.root
        if not target.exists():
            return 0
        removed = 0
        for path in target.rglob("*.json"):
            path.unlink()
            removed += 1
        return removed
