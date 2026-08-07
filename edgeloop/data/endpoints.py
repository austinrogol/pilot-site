"""The FMP endpoint registry.

This module exists so that every guess about FMP's URL space is *visible* rather
than scattered through the client as string literals. FMP runs two route
families concurrently -- the legacy ``/api/v3`` tree and the newer ``/stable``
tree -- and they do not agree on either path spelling or response field names.
This build targets ``/stable`` exclusively.

Every entry carries two independent verification axes, because they were
established by two different means and they can disagree:

``path_status``
    Do we know the URL is spelled correctly? Establishing this needs FMP's live
    docs or a live call.

``shape_status``
    Do we know what fields come back? Establishing this needs a real response
    body.

During the phase 1 build the sandbox had **no outbound network route to
financialmodelingprep.com** (the egress proxy refuses CONNECT for both the API
host and the docs host) and **no FMP_API_KEY**. So no path could be confirmed by
calling it. What *was* available is FMP's own MCP server, which is a different
transport onto the same account and the same backing data. Response bodies
pulled through it are real, which is why many entries below are
``ShapeStatus.LIVE`` while their paths are only ``PathStatus.INFERRED``.

Reading the table:

* ``PathStatus.DOCS`` -- the exact path string appears in FMP's published docs.
* ``PathStatus.INFERRED`` -- the path is derived from the MCP endpoint slug,
  which tracks the REST slug closely but is not guaranteed identical. **These
  are the ones to check first when a request 404s.** They are listed out in
  ``unverified_paths()`` and the phase 1 report prints them.
* ``ShapeStatus.LIVE`` -- a real response body was observed on this account on
  2026-08-07 and the pydantic model in ``schemas.py`` was written against it.
* ``ShapeStatus.UNKNOWN`` -- no body observed; the model is provisional.

``plan`` records what FMP's own MCP server reports as the entitlement, and
``PlanGate.BLOCKED`` entries are deliberately kept in the table rather than
deleted. A blocked endpoint that is invisible gets re-proposed every few months;
one that is present and annotated does not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

STABLE_BASE = "https://financialmodelingprep.com/stable"

# The legacy tree. Recorded for orientation only -- nothing in this build calls
# it. If a /stable path turns out not to exist, the v3 equivalent is the first
# place to look, but the response field names differ and schemas.py would need a
# parallel model. Do not silently fall back.
LEGACY_BASE = "https://financialmodelingprep.com/api/v3"


class PathStatus(str, Enum):
    DOCS = "docs"          # exact string found in FMP published documentation
    INFERRED = "inferred"  # derived from the MCP slug; unconfirmed
    LIVE = "live"          # a real HTTP call to this path returned 200


class ShapeStatus(str, Enum):
    LIVE = "live"        # real response body observed; schema written from it
    UNKNOWN = "unknown"  # no body seen; schema is provisional


class PlanGate(str, Enum):
    FREE = "free"        # observed working on this account
    BLOCKED = "blocked"  # observed refused, or documented above this tier


@dataclass(frozen=True)
class Endpoint:
    key: str
    path: str
    path_status: PathStatus
    shape_status: ShapeStatus
    plan: PlanGate
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    note: str = ""
    # Cache lifetime in seconds. Fundamentals change on filing dates, prices
    # change daily, treasury rates change daily. Nothing here is realtime-
    # critical: this is a research system, not an execution system.
    ttl_seconds: int = 24 * 3600

    @property
    def url(self) -> str:
        return f"{STABLE_BASE}/{self.path}"

    @property
    def blocked(self) -> bool:
        return self.plan is PlanGate.BLOCKED


def _e(*args, **kwargs) -> Endpoint:
    return Endpoint(*args, **kwargs)


# --------------------------------------------------------------------------
# Working set -- everything the analysis path is allowed to touch.
# --------------------------------------------------------------------------

_WORKING: tuple[Endpoint, ...] = (
    _e(
        key="quote",
        path="quote",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.LIVE,
        plan=PlanGate.FREE,
        required=("symbol",),
        note="Spot price, day range, 50/200d averages, marketCap. timestamp is unix seconds.",
        ttl_seconds=900,
    ),
    _e(
        key="historical_price_light",
        path="historical-price-eod/light",
        path_status=PathStatus.DOCS,
        shape_status=ShapeStatus.LIVE,
        plan=PlanGate.FREE,
        required=("symbol",),
        optional=("from", "to"),
        note=(
            "The volatility workhorse. Returns {symbol,date,price,volume} -- note "
            "the close field is called 'price', not 'close'. Split/dividend "
            "adjusted. Newest row first."
        ),
    ),
    _e(
        key="historical_price_full",
        path="historical-price-eod/full",
        path_status=PathStatus.DOCS,
        shape_status=ShapeStatus.LIVE,
        plan=PlanGate.FREE,
        required=("symbol",),
        optional=("from", "to"),
        note=(
            "OHLC + vwap + change. Needed for the corporate-action sanity checks "
            "in quant/returns.py, which compare intraday range against the "
            "close-to-close jump to tell a split from a real move."
        ),
    ),
    _e(
        key="profile",
        path="profile",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.LIVE,
        plan=PlanGate.FREE,
        required=("symbol",),
        note=(
            "Carries beta (CAPM drift) and averageVolume (the liquidity/exit-"
            "capacity sizing constraint). Both are load-bearing; neither appears "
            "in key-metrics-ttm."
        ),
    ),
    _e(
        key="peers",
        path="stock-peers",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.LIVE,
        plan=PlanGate.FREE,
        required=("symbol",),
        note="Returns {symbol,companyName,price,mktCap} -- 'mktCap' here, 'marketCap' in quote.",
    ),
    _e(
        key="key_metrics_ttm",
        path="key-metrics-ttm",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.LIVE,
        plan=PlanGate.FREE,
        required=("symbol",),
        note=(
            "Every field is suffixed TTM (earningsYieldTTM, freeCashFlowYieldTTM). "
            "Those two feed the 1y/3y fundamental drift leg."
        ),
    ),
    _e(
        key="ratios_ttm",
        path="ratios-ttm",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.UNKNOWN,
        plan=PlanGate.FREE,
        required=("symbol",),
        note=(
            "PATH RISK: FMP's docs page for this is slugged 'metrics-ratios-ttm' "
            "while the REST path is believed to be 'ratios-ttm'. Unresolved "
            "without a live call -- see PHASE1_REPORT."
        ),
    ),
    _e(
        key="income_statement",
        path="income-statement",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.LIVE,
        plan=PlanGate.FREE,
        required=("symbol",),
        optional=("period", "limit"),
        note=(
            "Carries BOTH 'date' (fiscal period end) and 'filingDate'/'acceptedDate'. "
            "Point-in-time discipline (constraint 6) means data_asof must come from "
            "acceptedDate, never from date -- they differ by a month for NVDA."
        ),
        ttl_seconds=7 * 24 * 3600,
    ),
    _e(
        key="balance_sheet",
        path="balance-sheet-statement",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.UNKNOWN,
        plan=PlanGate.FREE,
        required=("symbol",),
        optional=("period", "limit"),
        ttl_seconds=7 * 24 * 3600,
    ),
    _e(
        key="cash_flow",
        path="cash-flow-statement",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.UNKNOWN,
        plan=PlanGate.FREE,
        required=("symbol",),
        optional=("period", "limit"),
        ttl_seconds=7 * 24 * 3600,
    ),
    _e(
        key="grades",
        path="grades",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.UNKNOWN,
        plan=PlanGate.FREE,
        required=("symbol",),
        note=(
            "Stored for the research record only. Analyst revisions are NOT a "
            "drift input at any horizon -- non-negotiable 1."
        ),
    ),
    _e(
        key="price_target_consensus",
        path="price-target-consensus",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.LIVE,
        plan=PlanGate.FREE,
        required=("symbol",),
        note=(
            "Returns targetHigh/Low/Consensus/Median. Displayed as third-party "
            "opinion; never folded into mu. Same reason as grades."
        ),
    ),
    _e(
        key="earnings_calendar",
        path="earnings-calendar",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.UNKNOWN,
        plan=PlanGate.FREE,
        optional=("from", "to", "symbol"),
        note="Event-risk flag: a forecast horizon that straddles an earnings date is annotated.",
    ),
    _e(
        key="dividends_calendar",
        path="dividends-calendar",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.UNKNOWN,
        plan=PlanGate.FREE,
        optional=("from", "to", "symbol"),
    ),
    _e(
        key="news_stock",
        path="news/stock",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.UNKNOWN,
        plan=PlanGate.FREE,
        optional=("symbols", "from", "to", "limit"),
        note=(
            "Stored as research context. NOT scored, NOT sentiment-tagged, NOT an "
            "input to mu -- explicitly out of scope."
        ),
    ),
    _e(
        key="sec_filings",
        path="sec-filings-search/symbol",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.UNKNOWN,
        plan=PlanGate.FREE,
        required=("symbol",),
        optional=("from", "to", "limit"),
    ),
    _e(
        key="insider_trading",
        path="insider-trading/search",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.UNKNOWN,
        plan=PlanGate.FREE,
        optional=("symbol", "limit", "page"),
    ),
    _e(
        key="treasury_rates",
        path="treasury-rates",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.LIVE,
        plan=PlanGate.FREE,
        optional=("from", "to"),
        note=(
            "Risk-free leg of CAPM. One row per date with month1..year30 columns, "
            "quoted in PERCENT (4.65 means 4.65%), newest first."
        ),
    ),
    _e(
        key="economic_indicators",
        path="economic-indicators",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.UNKNOWN,
        plan=PlanGate.FREE,
        required=("name",),
        optional=("from", "to"),
    ),
    _e(
        key="market_risk_premium",
        path="market-risk-premium",
        path_status=PathStatus.INFERRED,
        shape_status=ShapeStatus.LIVE,
        plan=PlanGate.FREE,
        note=(
            "Equity risk premium by country; the market leg of CAPM. Quoted in "
            "PERCENT. WARNING: the country filter is ignored server-side -- the "
            "call returns ~200 rows for every country and the client filters. "
            "Cache this hard; it is one response for the whole universe."
        ),
        ttl_seconds=7 * 24 * 3600,
    ),
)


# --------------------------------------------------------------------------
# Blocked set -- present so the gap stays visible. Requesting one of these
# raises rather than returning empty, so a caller cannot mistake "your plan
# does not cover this" for "the company has no such data".
# --------------------------------------------------------------------------

_BLOCKED: tuple[Endpoint, ...] = (
    _e(key="technical_indicators", path="technical-indicators", path_status=PathStatus.INFERRED,
       shape_status=ShapeStatus.UNKNOWN, plan=PlanGate.BLOCKED,
       note="Starter+. Verified refused on this account 2026-08-07. Irrelevant: "
            "volatility is computed from raw prices, which is more reproducible anyway."),
    _e(key="earnings_transcripts", path="earning-call-transcript", path_status=PathStatus.INFERRED,
       shape_status=ShapeStatus.UNKNOWN, plan=PlanGate.BLOCKED, note="Ultimate+."),
    _e(key="form_13f", path="institutional-ownership/extract", path_status=PathStatus.INFERRED,
       shape_status=ShapeStatus.UNKNOWN, plan=PlanGate.BLOCKED, note="Ultimate+."),
    _e(key="cot", path="commitment-of-traders-report", path_status=PathStatus.INFERRED,
       shape_status=ShapeStatus.UNKNOWN, plan=PlanGate.BLOCKED, note="Premium+."),
    _e(key="esg", path="esg-disclosures", path_status=PathStatus.INFERRED,
       shape_status=ShapeStatus.UNKNOWN, plan=PlanGate.BLOCKED, note="Ultimate+."),
    _e(key="tipranks", path="tipranks", path_status=PathStatus.INFERRED,
       shape_status=ShapeStatus.UNKNOWN, plan=PlanGate.BLOCKED, note="Paid add-on."),
)


REGISTRY: dict[str, Endpoint] = {e.key: e for e in (*_WORKING, *_BLOCKED)}


class EndpointBlocked(RuntimeError):
    """Raised when code asks for data this FMP plan does not sell.

    Deliberately loud. The alternative -- returning None -- lets a plan gap
    silently become a null in a forecast row.
    """


def get(key: str) -> Endpoint:
    try:
        endpoint = REGISTRY[key]
    except KeyError:
        raise KeyError(
            f"unknown endpoint {key!r}; known keys: {sorted(REGISTRY)}"
        ) from None
    if endpoint.blocked:
        raise EndpointBlocked(
            f"{key!r} is not available on this FMP plan ({endpoint.note}). "
            "This is a data gap, not a bug. Do not substitute a proxy for it."
        )
    return endpoint


def unverified_paths() -> list[Endpoint]:
    """Endpoints whose URL has never been confirmed by docs or a live 200.

    The phase 1 report prints this. It is the honest answer to "what did you
    have to guess at".
    """
    return [e for e in _WORKING if e.path_status is PathStatus.INFERRED]


def unverified_shapes() -> list[Endpoint]:
    """Endpoints whose response body has never been observed."""
    return [e for e in _WORKING if e.shape_status is ShapeStatus.UNKNOWN]


def blocked() -> list[Endpoint]:
    return list(_BLOCKED)


# --------------------------------------------------------------------------
# The options gap.
# --------------------------------------------------------------------------

OPTIONS_AVAILABILITY = (
    "FMP sells no options data at any tier: no chains, no implied vol, no skew, "
    "no open interest. There is therefore no ImpliedVol implementation of the "
    "VolatilitySource interface, and there cannot be one against this vendor. "
    "See quant/volatility.py -- the empty slot is deliberate and is the largest "
    "single gap in the system."
)
