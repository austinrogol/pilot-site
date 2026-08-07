"""The FMP REST client.

Order of operations for every fetch, and the order matters:

1. **Cache** -- keyed on (endpoint, params, UTC date). A fresh hit costs nothing
   and never touches the governor.
2. **Governor** -- a call that would exceed the trailing-24h budget is refused
   *before* the socket is opened, not after.
3. **Transport** -- the only thing that sees the API key.
4. **Parse** -- into the typed models in schemas.py.
5. **Provenance** -- source, fetched_at, data_asof, quality, and the missing[]
   register, attached to every result.

If the governor refuses and an expired cache entry exists, the entry is served
with ``Quality.STALE`` and a note saying exactly how old it is. That is not a
silent carry-forward -- constraint 5 forbids *silent*, and this is labelled at
every layer up to the UI. The alternative, failing the whole analysis because a
budget ran out, throws away good data for no gain.

Budget: a single ticker analysis is meant to cost under 8 uncached calls.
``CallBudget`` counts them so the claim is measured rather than asserted; the
phase 1 proof prints the count.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generic, Sequence, TypeVar

from ..config import Settings, load_settings
from . import endpoints as ep
from .cache import DiskCache
from .governor import Decision, RateGovernor
from .provenance import Provenance, Quality, utcnow
from .schemas import (
    AnalystPriceTarget,
    CompanyProfile,
    FmpModel,
    IncomeStatement,
    KeyMetricsTTM,
    MarketRiskPremium,
    Peer,
    PriceBarFull,
    PriceBarLight,
    Quote,
    TreasuryRate,
)
from .transport import FixtureTransport, HttpxTransport, Response, Transport, TransportError

M = TypeVar("M", bound=FmpModel)

# How many times to wait out the sub-second spacing throttle before giving up.
_SPACING_WAIT_ATTEMPTS = 5


class FmpError(RuntimeError):
    """A request failed in a way the caller must handle explicitly."""


class RateLimited(FmpError):
    """The local governor refused, or FMP returned 429."""


@dataclass
class Fetched(Generic[M]):
    """A parsed response plus everything needed to judge it."""

    rows: list[M]
    provenance: Provenance

    @property
    def first(self) -> M | None:
        return self.rows[0] if self.rows else None

    def require_first(self) -> M:
        if not self.rows:
            raise FmpError(
                f"{self.provenance.endpoint} returned no rows for "
                f"{self.provenance.params}; refusing to substitute a default"
            )
        return self.rows[0]


@dataclass
class CallBudget:
    """Counts what a run actually spent."""

    uncached: int = 0
    cached: int = 0
    stale_served: int = 0
    endpoints: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.uncached + self.cached

    def render(self) -> str:
        return (
            f"{self.uncached} uncached / {self.cached} cached "
            f"({self.stale_served} served stale) across {len(self.endpoints)} requests"
        )


class FmpClient:
    def __init__(
        self,
        settings: Settings | None = None,
        transport: Transport | None = None,
        cache: DiskCache | None = None,
        governor: RateGovernor | None = None,
    ):
        self.settings = settings or load_settings()
        self.cache = cache or DiskCache(self.settings.cache_dir)
        self.governor = governor or RateGovernor(
            self.settings.governor_state_path,
            self.settings.fmp.max_calls_per_day,
            self.settings.fmp.min_seconds_between_calls,
        )
        self._transport = transport
        self.budget = CallBudget()

    # -- construction helpers ----------------------------------------------

    @classmethod
    def from_fixtures(cls, fixture_dir: Path, settings: Settings | None = None) -> FmpClient:
        """A client backed by recorded bodies. No network, no key."""
        return cls(settings=settings, transport=FixtureTransport(fixture_dir))

    @property
    def transport(self) -> Transport:
        if self._transport is None:
            if not self.settings.fmp.configured:
                raise FmpError(
                    "FMP_API_KEY is not set. Set it in the environment -- it must "
                    "never be written into the repo. For an offline run use "
                    "FmpClient.from_fixtures()."
                )
            self._transport = HttpxTransport(
                self.settings.fmp.api_key, self.settings.fmp.timeout_seconds
            )
        return self._transport

    async def aclose(self) -> None:
        if self._transport is not None:
            await self._transport.aclose()

    async def __aenter__(self) -> FmpClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # -- the core fetch -----------------------------------------------------

    async def fetch(
        self,
        endpoint_key: str,
        model: type[M],
        params: dict[str, Any] | None = None,
        expect_fields: tuple[str, ...] = (),
    ) -> Fetched[M]:
        endpoint = ep.get(endpoint_key)  # raises EndpointBlocked for gated data
        params = {k: v for k, v in (params or {}).items() if v is not None}

        missing_required = [p for p in endpoint.required if p not in params]
        if missing_required:
            raise FmpError(
                f"{endpoint_key} requires {missing_required}; got {sorted(params)}"
            )

        now = utcnow()
        key = self.cache.build_key(endpoint_key, params, now.date().isoformat())
        entry = self.cache.get(key)

        if entry is not None and not entry.expired(now):
            self.budget.cached += 1
            self.budget.endpoints.append(endpoint_key)
            return self._parse(
                endpoint_key, params, entry.body, model, expect_fields,
                fetched_at=entry.stored_at, cache_hit=True,
            )

        decision = await self._acquire_slot(now)
        if not decision.permitted:
            if entry is not None:
                # Expired but present. Serve it, loudly.
                self.budget.cached += 1
                self.budget.stale_served += 1
                self.budget.endpoints.append(endpoint_key)
                result = self._parse(
                    endpoint_key, params, entry.body, model, expect_fields,
                    fetched_at=entry.stored_at, cache_hit=True,
                )
                result.provenance.quality = Quality.STALE
                result.provenance.note = (
                    f"served from cache past its {entry.ttl_seconds}s TTL "
                    f"({entry.age_seconds(now) / 3600:.1f}h old) because the rate "
                    f"governor refused a refetch -- {decision.reason}"
                )
                return result
            raise RateLimited(
                f"rate governor refused {endpoint_key} and no cached body exists. "
                f"{decision.reason}"
            )

        response = await self._get_with_retries(endpoint, params)
        self.budget.uncached += 1
        self.budget.endpoints.append(endpoint_key)
        self.cache.put(key, endpoint_key, params, response.body, endpoint.ttl_seconds, now)
        return self._parse(
            endpoint_key, params, response.body, model, expect_fields,
            fetched_at=now, cache_hit=False,
        )

    async def _acquire_slot(self, now: datetime) -> "Decision":
        """Get permission for one call, waiting out the spacing throttle.

        The daily cap is a budget and refuses. The minimum spacing is a
        politeness throttle and only delays -- turning it into a refusal would
        make a burst of cheap cached-miss calls fail for no reason. Waits are
        sub-second by construction and bounded by a small number of attempts so
        a pathological config cannot hang a request forever.
        """
        for _ in range(_SPACING_WAIT_ATTEMPTS):
            decision = self.governor.check_and_record(now)
            if decision.permitted or decision.hard_block:
                return decision
            await asyncio.sleep(decision.retry_after_seconds or 0.05)
            now = utcnow()
        return decision

    async def _get_with_retries(self, endpoint: ep.Endpoint, params: dict[str, Any]) -> Response:
        last: Exception | None = None
        for attempt in range(self.settings.fmp.max_retries):
            try:
                response = await self.transport.get(endpoint.url, params)
            except TransportError as exc:
                last = exc
                await asyncio.sleep(2**attempt)
                continue

            if response.status == 200:
                return response
            if response.status in (401, 403):
                raise FmpError(
                    f"FMP refused {endpoint.key} with {response.status}. Either the "
                    "key is invalid or this endpoint is above the current plan. "
                    f"Registry records it as plan={endpoint.plan.value}, "
                    f"path_status={endpoint.path_status.value}."
                )
            if response.status == 404:
                raise FmpError(
                    f"FMP returned 404 for {endpoint.url}. The registry marks this "
                    f"path as {endpoint.path_status.value} -- if it is 'inferred', "
                    "the path spelling is the first thing to check. Do not fall "
                    "back to /api/v3 silently; the response fields differ."
                )
            if response.status == 429 or response.status >= 500:
                last = FmpError(f"FMP returned {response.status} for {endpoint.key}")
                await asyncio.sleep(2**attempt)
                continue
            raise FmpError(f"FMP returned {response.status} for {endpoint.key}")

        raise FmpError(
            f"{endpoint.key} failed after {self.settings.fmp.max_retries} attempts: {last}"
        )

    def _parse(
        self,
        endpoint_key: str,
        params: dict[str, Any],
        body: Any,
        model: type[M],
        expect_fields: tuple[str, ...],
        fetched_at: datetime,
        cache_hit: bool,
    ) -> Fetched[M]:
        provenance = Provenance(
            source="fmp",
            endpoint=endpoint_key,
            params=params,
            fetched_at=fetched_at,
            data_asof=None,
            cache_hit=cache_hit,
        )

        if isinstance(body, dict) and "Error Message" in body:
            provenance.quality = Quality.MISSING
            provenance.add_missing("*", str(body["Error Message"]))
            return Fetched(rows=[], provenance=provenance)

        raw_rows: Sequence[Any]
        if isinstance(body, list):
            raw_rows = body
        elif isinstance(body, dict):
            raw_rows = [body]
        else:
            provenance.quality = Quality.MISSING
            provenance.add_missing("*", f"unexpected response type {type(body).__name__}")
            return Fetched(rows=[], provenance=provenance)

        rows: list[M] = []
        for index, raw in enumerate(raw_rows):
            try:
                rows.append(model.model_validate(raw))
            except Exception as exc:  # pydantic ValidationError and friends
                provenance.add_missing(f"[{index}]", f"row failed validation: {exc}")

        if not rows:
            provenance.quality = Quality.MISSING
            if not provenance.missing:
                provenance.add_missing("*", "source returned zero rows")
            return Fetched(rows=[], provenance=provenance)

        # data_asof is the newest point-in-time stamp across the rows. None if
        # the source published none -- recorded, never defaulted to now.
        stamps = [s for s in (row.as_of() for row in rows) if s is not None]
        if stamps:
            provenance.data_asof = max(stamps)
            if provenance.data_asof > fetched_at:
                # A daily bar stamped end-of-UTC-day legitimately reads as
                # "after" a mid-afternoon fetch. Clamp rather than reject: the
                # data is real, our end-of-day convention is the coarse part.
                provenance.note = (
                    f"data_asof clamped from {provenance.data_asof.isoformat()} to "
                    "fetch time (EOD bars are stamped end-of-UTC-day)"
                )
                provenance.data_asof = fetched_at
        else:
            provenance.add_missing(
                "data_asof",
                "source published no timestamp for this record; point-in-time "
                "position is unknown and was NOT defaulted to the fetch time",
            )

        for name, reason in rows[0].null_fields(expect_fields):
            provenance.add_missing(name, reason)

        return Fetched(rows=rows, provenance=provenance)

    # -- typed convenience methods -----------------------------------------
    #
    # expect_fields names the fields this system actually depends on, so a null
    # in one of them becomes a visible missing[] entry rather than a None that
    # surfaces as a crash three modules later.

    async def quote(self, symbol: str) -> Fetched[Quote]:
        return await self.fetch(
            "quote", Quote, {"symbol": symbol}, expect_fields=("price", "timestamp")
        )

    async def price_history(
        self, symbol: str, start: str | None = None, end: str | None = None
    ) -> Fetched[PriceBarLight]:
        """Adjusted daily closes -- the volatility input."""
        return await self.fetch(
            "historical_price_light",
            PriceBarLight,
            {"symbol": symbol, "from": start, "to": end},
            expect_fields=("price",),
        )

    async def price_history_full(
        self, symbol: str, start: str | None = None, end: str | None = None
    ) -> Fetched[PriceBarFull]:
        """OHLC -- needed for corporate-action sanity checks."""
        return await self.fetch(
            "historical_price_full",
            PriceBarFull,
            {"symbol": symbol, "from": start, "to": end},
            expect_fields=("open", "high", "low", "close"),
        )

    async def profile(self, symbol: str) -> Fetched[CompanyProfile]:
        return await self.fetch(
            "profile",
            CompanyProfile,
            {"symbol": symbol},
            expect_fields=("beta", "averageVolume", "marketCap"),
        )

    async def peers(self, symbol: str) -> Fetched[Peer]:
        return await self.fetch("peers", Peer, {"symbol": symbol})

    async def key_metrics_ttm(self, symbol: str) -> Fetched[KeyMetricsTTM]:
        return await self.fetch(
            "key_metrics_ttm",
            KeyMetricsTTM,
            {"symbol": symbol},
            expect_fields=("earningsYieldTTM", "freeCashFlowYieldTTM"),
        )

    async def income_statement(
        self, symbol: str, period: str = "annual", limit: int = 4
    ) -> Fetched[IncomeStatement]:
        return await self.fetch(
            "income_statement",
            IncomeStatement,
            {"symbol": symbol, "period": period, "limit": limit},
            expect_fields=("acceptedDate", "revenue", "netIncome"),
        )

    async def price_target_consensus(self, symbol: str) -> Fetched[AnalystPriceTarget]:
        return await self.fetch(
            "price_target_consensus", AnalystPriceTarget, {"symbol": symbol}
        )

    async def treasury_rates(
        self, start: str | None = None, end: str | None = None
    ) -> Fetched[TreasuryRate]:
        return await self.fetch(
            "treasury_rates",
            TreasuryRate,
            {"from": start, "to": end},
            expect_fields=("year10",),
        )

    async def market_risk_premium(self, country: str = "United States") -> Fetched[MarketRiskPremium]:
        """Equity risk premium for one country.

        The endpoint ignores its country filter and returns every country, so
        the filter happens here. The provenance records the full row count so
        the client-side filtering is not invisible.
        """
        result = await self.fetch("market_risk_premium", MarketRiskPremium, {})
        total = len(result.rows)
        matched = [r for r in result.rows if r.country == country]
        if not matched:
            result.provenance.add_missing(
                "country",
                f"{country!r} not present among {total} countries returned",
            )
        note = (
            f"server-side country filter is not honoured by this endpoint; "
            f"filtered {total} rows to {len(matched)} client-side for {country!r}"
        )
        result.provenance.note = f"{result.provenance.note}; {note}".lstrip("; ")
        return Fetched(rows=matched, provenance=result.provenance)
