"""Configuration. Everything tunable lives here, nothing tunable lives in a function.

The spec is explicit that the drift shrinkage weights are *priors*, not
constants, and must be visible as such. They are declared here even though
quant/drift.py is a phase 2 module, so that when drift lands there is no
temptation to bury 0.78 in a return statement.

Secrets come from the environment only. FMP_API_KEY is read once, is never
logged, never serialised into a provenance record, and never appears in a
response body. `Settings.redacted()` is what gets printed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a float, got {raw!r}") from None


@dataclass(frozen=True)
class DriftPriors:
    """Shrinkage weights toward the market-implied CAPM rate, by horizon.

    These are priors chosen by the operator, not estimates from data. They say
    how much a fundamental view is allowed to move the forecast away from "the
    market is right". Higher = more shrinkage = more deference to CAPM.

    The <=21d case is not represented here because it is not a blend and must
    never become one: at or under 21 days drift IS the CAPM rate, full stop.
    See non-negotiable 1 and the docstring in quant/drift.py.
    """

    shrink_1y: float = 0.78
    shrink_3y: float = 0.60

    # Horizon boundary for the no-directional-forecast rule. Changing this is a
    # research decision that needs evidence, not a config tweak.
    no_forecast_horizon_days: int = 21

    def __post_init__(self) -> None:
        for name in ("shrink_1y", "shrink_3y"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0,1], got {value}")


@dataclass(frozen=True)
class VolatilityConfig:
    """Thresholds for the GARCH identification test (non-negotiable 3)."""

    # Below this many observations the fit is rejected outright, regardless of
    # what the optimiser reports. 47 NVDA returns pinned alpha and beta to the
    # grid edges and produced a 1.4-day half-life that meant nothing.
    min_observations: int = 150

    # Two-sided t-stat each of alpha and beta must clear for the fit to be used.
    min_param_tstat: float = 2.0

    # Student-t degrees of freedom clamp. Below 3.5 the variance of the
    # forecast distribution gets unstable; above 30 it is Gaussian anyway.
    nu_floor: float = 3.5
    nu_ceiling: float = 30.0

    # EWMA fallback decay (RiskMetrics daily convention).
    ewma_lambda: float = 0.94


@dataclass(frozen=True)
class LedgerConfig:
    """Calibration reporting gates (non-negotiable 4)."""

    # No coverage statistic is reported below this many resolved forecasts at a
    # given horizon. The ledger starts empty and stays visibly empty.
    min_resolved_for_calibration: int = 30


@dataclass(frozen=True)
class FmpConfig:
    api_key: str | None = None
    timeout_seconds: float = 20.0
    max_retries: int = 3

    # Rate governor. Free tier is a few hundred calls a day; this is a
    # self-imposed cap well under it, tuned by the operator by hand.
    max_calls_per_day: int = 240
    min_seconds_between_calls: float = 0.25

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class Settings:
    fmp: FmpConfig = field(default_factory=FmpConfig)
    drift: DriftPriors = field(default_factory=DriftPriors)
    volatility: VolatilityConfig = field(default_factory=VolatilityConfig)
    ledger: LedgerConfig = field(default_factory=LedgerConfig)

    database_url: str = f"sqlite:///{REPO_ROOT / 'var' / 'edgeloop.sqlite'}"
    cache_dir: Path = REPO_ROOT / "var" / "cache"
    governor_state_path: Path = REPO_ROOT / "var" / "governor_state.json"

    model_version: str = "edgeloop2-0.1.0-phase1"

    def redacted(self) -> dict:
        """Everything except the key, safe to log or return over HTTP."""
        payload = asdict(self)
        payload["fmp"]["api_key"] = "<set>" if self.fmp.configured else "<unset>"
        payload["cache_dir"] = str(self.cache_dir)
        payload["governor_state_path"] = str(self.governor_state_path)
        # A Postgres DATABASE_URL carries a password in the netloc.
        payload["database_url"] = _redact_url(self.database_url)
        return payload


def _redact_url(url: str) -> str:
    if "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    creds, _, host = rest.rpartition("@")
    if ":" in creds:
        user, _, _ = creds.partition(":")
        creds = f"{user}:<redacted>"
    return f"{scheme}://{creds}@{host}"


def load_settings() -> Settings:
    """Build settings from the environment.

    DATABASE_URL is the single switch between SQLite (default, local) and
    Postgres (Railway). Nothing else changes shape.
    """
    database_url = os.environ.get("DATABASE_URL") or str(
        Settings.__dataclass_fields__["database_url"].default
    )
    return Settings(
        fmp=FmpConfig(
            api_key=os.environ.get("FMP_API_KEY") or None,
            timeout_seconds=_env_float("FMP_TIMEOUT_SECONDS", 20.0),
            max_retries=_env_int("FMP_MAX_RETRIES", 3),
            max_calls_per_day=_env_int("FMP_MAX_CALLS_PER_DAY", 240),
            min_seconds_between_calls=_env_float("FMP_MIN_SECONDS_BETWEEN_CALLS", 0.25),
        ),
        drift=DriftPriors(
            shrink_1y=_env_float("EDGELOOP_SHRINK_1Y", 0.78),
            shrink_3y=_env_float("EDGELOOP_SHRINK_3Y", 0.60),
        ),
        database_url=database_url,
    )
