"""Typed FMP responses.

Every model here was written against a real response body observed on this
account on 2026-08-07, except where the class docstring says otherwise. Field
names follow FMP's spelling exactly, including its inconsistencies -- the light
price chart calls the close ``price``, ``quote`` calls market cap ``marketCap``
while ``stock-peers`` calls it ``mktCap``. Renaming those in the model would
hide the vendor's shape from anyone debugging a response; they are renamed at
the point of use instead.

Every field that is not structurally guaranteed is Optional with a None default.
That is constraint 5 in the type system: a field the source did not return
becomes None, and the client turns each None into a ``MissingField`` entry. No
model has a default that invents a value.

Each model exposes ``as_of()``, which returns the point-in-time timestamp for
that record -- the instant the data was *true*, not when we fetched it.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from pydantic import BaseModel, ConfigDict, Field


class FmpModel(BaseModel):
    # FMP adds fields without warning. Ignoring extras keeps a new column from
    # breaking a running deployment; the fields we depend on are all declared.
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    def as_of(self) -> datetime | None:
        return None

    def null_fields(self, expected: tuple[str, ...]) -> list[tuple[str, str]]:
        """Which of ``expected`` came back null. Feeds Provenance.missing."""
        out: list[tuple[str, str]] = []
        for name in expected:
            if getattr(self, name, None) is None:
                out.append((name, "source returned null or omitted the field"))
        return out


def _eod(day: date) -> datetime:
    """A daily bar is true as of the close. Treat that as end of the UTC day.

    Deliberately coarse: FMP publishes EOD rows with a bare date and no
    exchange timezone, so pretending to know 16:00 America/New_York would be
    inventing precision the source did not supply.
    """
    return datetime.combine(day, time(23, 59, 59), tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------


class Quote(FmpModel):
    """/stable/quote -- shape verified live."""

    symbol: str
    name: str | None = None
    price: float | None = None
    change: float | None = None
    changePercentage: float | None = None
    volume: float | None = None
    dayLow: float | None = None
    dayHigh: float | None = None
    yearHigh: float | None = None
    yearLow: float | None = None
    marketCap: float | None = None
    priceAvg50: float | None = None
    priceAvg200: float | None = None
    exchange: str | None = None
    open: float | None = None
    previousClose: float | None = None
    timestamp: int | None = None

    def as_of(self) -> datetime | None:
        if self.timestamp is None:
            return None
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)


class PriceBarLight(FmpModel):
    """/stable/historical-price-eod/light -- shape verified live.

    The close is named ``price``. Split and dividend adjusted.
    """

    symbol: str | None = None
    date: date
    price: float | None = None
    volume: float | None = None

    def as_of(self) -> datetime | None:
        return _eod(self.date)


class PriceBarFull(FmpModel):
    """/stable/historical-price-eod/full -- shape verified live.

    OHLC is what lets quant/returns.py separate a split from a real move: a
    ~50% close-to-close gap with an intraday range of 1% is a corporate action,
    not a crash.
    """

    symbol: str | None = None
    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    change: float | None = None
    changePercent: float | None = None
    vwap: float | None = None

    def as_of(self) -> datetime | None:
        return _eod(self.date)


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------


class CompanyProfile(FmpModel):
    """/stable/profile -- shape verified live.

    ``beta`` and ``averageVolume`` are the two load-bearing fields: beta drives
    the CAPM drift, averageVolume drives the liquidity/exit-capacity sizing
    constraint. Neither is available from key-metrics-ttm.

    The profile carries no timestamp of its own, so ``as_of()`` is None and the
    caller must record that explicitly rather than assume "now".
    """

    symbol: str
    companyName: str | None = None
    price: float | None = None
    marketCap: float | None = None
    beta: float | None = None
    lastDividend: float | None = None
    volume: float | None = None
    averageVolume: float | None = None
    currency: str | None = None
    cik: str | None = None
    exchange: str | None = None
    exchangeFullName: str | None = None
    industry: str | None = None
    sector: str | None = None
    country: str | None = None
    ipoDate: date | None = None
    isEtf: bool | None = None
    isFund: bool | None = None
    isActivelyTrading: bool | None = None


class Peer(FmpModel):
    """/stable/stock-peers -- shape verified live. Market cap is ``mktCap`` here."""

    symbol: str
    companyName: str | None = None
    price: float | None = None
    mktCap: float | None = None


class KeyMetricsTTM(FmpModel):
    """/stable/key-metrics-ttm -- shape verified live.

    Only the fields the quant core consumes are declared; FMP returns ~45.
    ``earningsYieldTTM`` and ``freeCashFlowYieldTTM`` are the fundamental-yield
    leg of the 1y/3y drift blend.
    """

    symbol: str | None = None
    marketCap: float | None = None
    enterpriseValueTTM: float | None = None
    earningsYieldTTM: float | None = None
    freeCashFlowYieldTTM: float | None = None
    returnOnEquityTTM: float | None = None
    returnOnInvestedCapitalTTM: float | None = None
    currentRatioTTM: float | None = None
    netDebtToEBITDATTM: float | None = None
    incomeQualityTTM: float | None = None
    evToEBITDATTM: float | None = None
    evToSalesTTM: float | None = None


# ---------------------------------------------------------------------------
# Fundamentals -- the point-in-time critical path
# ---------------------------------------------------------------------------


class IncomeStatement(FmpModel):
    """/stable/income-statement -- shape verified live.

    THE point-in-time model. ``date`` is the fiscal period end; ``filingDate``
    and ``acceptedDate`` are when the world could first have known. For NVDA
    FY2026 those are 2026-01-25 and 2026-02-25 respectively -- a month apart.
    ``as_of()`` returns the acceptance instant precisely so that no consumer can
    accidentally treat the period end as the knowledge date.
    """

    symbol: str
    date: date
    filingDate: date | None = None
    acceptedDate: datetime | None = None
    reportedCurrency: str | None = None
    cik: str | None = None
    fiscalYear: str | None = None
    period: str | None = None

    revenue: float | None = None
    grossProfit: float | None = None
    operatingIncome: float | None = None
    netIncome: float | None = None
    ebitda: float | None = None
    eps: float | None = None
    epsDiluted: float | None = None
    weightedAverageShsOut: float | None = None
    weightedAverageShsOutDil: float | None = None

    def as_of(self) -> datetime | None:
        """Knowledge date, never the fiscal period end.

        Returns None rather than falling back to ``date`` when neither
        acceptance nor filing date is present. A null here is honest; a
        fallback to the period end would silently manufacture lookahead.
        """
        if self.acceptedDate is not None:
            accepted = self.acceptedDate
            if accepted.tzinfo is None:
                # FMP returns "2026-02-25 16:42:19" with no zone. It is SEC
                # EDGAR acceptance, which is US Eastern. We do not have a tz
                # database guarantee here, so treat it as UTC and accept that
                # this is coarse by a few hours -- documented, not hidden.
                accepted = accepted.replace(tzinfo=timezone.utc)
            return accepted
        if self.filingDate is not None:
            return _eod(self.filingDate)
        return None


class AnalystPriceTarget(FmpModel):
    """/stable/price-target-consensus -- shape verified live.

    Recorded as third-party opinion for the research log. Never an input to mu:
    a directional analyst signal at short horizons is exactly what
    non-negotiable 1 forbids.
    """

    symbol: str
    targetHigh: float | None = None
    targetLow: float | None = None
    targetConsensus: float | None = None
    targetMedian: float | None = None


# ---------------------------------------------------------------------------
# Macro
# ---------------------------------------------------------------------------


class TreasuryRate(FmpModel):
    """/stable/treasury-rates -- shape verified live.

    Rates are quoted in PERCENT (4.65 means 4.65%). Converting to a decimal is
    the caller's job and is done once, in the drift module.
    """

    date: date
    month1: float | None = None
    month2: float | None = None
    month3: float | None = None
    month6: float | None = None
    year1: float | None = None
    year2: float | None = None
    year3: float | None = None
    year5: float | None = None
    year7: float | None = None
    year10: float | None = None
    year20: float | None = None
    year30: float | None = None

    def as_of(self) -> datetime | None:
        return _eod(self.date)

    def for_horizon_days(self, horizon_days: int) -> tuple[float | None, str]:
        """Nearest maturity at or above the horizon, and which one was used.

        Returns the rate in percent, plus the field name so the choice lands in
        the provenance record instead of being invisible.
        """
        ladder = (
            (30, "month1"), (60, "month2"), (91, "month3"), (182, "month6"),
            (365, "year1"), (730, "year2"), (1095, "year3"), (1825, "year5"),
            (2555, "year7"), (3650, "year10"), (7300, "year20"), (10950, "year30"),
        )
        for days, name in ladder:
            if horizon_days <= days:
                value = getattr(self, name)
                if value is not None:
                    return value, name
        return self.year30, "year30"


class MarketRiskPremium(FmpModel):
    """/stable/market-risk-premium -- shape verified live.

    Quoted in PERCENT. The endpoint ignores its country filter and returns
    every country, so the client filters client-side.

    Carries no date field at all, which is a real point-in-time gap: we know
    when we fetched it but not when Damodaran last revised it. ``as_of()``
    returns None and the client records the absence rather than stamping it
    with the fetch time.
    """

    country: str
    continent: str | None = None
    countryRiskPremium: float | None = None
    totalEquityRiskPremium: float | None = None
