"""SQLAlchemy 2.x schema.

SQLite by default, Postgres via DATABASE_URL. Nothing in here is dialect
specific except the enforcement note on the append-only rule.

Two structural commitments are enforced by the database rather than by
convention, because a convention is a thing a future contributor can forget:

**No lookahead.** ``forecasts`` carries a CHECK constraint that ``data_asof <=
created_at``. A forecast that claims to have been generated from data newer than
itself is the single defect that would make every future backtest illegitimate,
so the database refuses to store one. This is test 5.

**Forecasts are append-only.** A forecast row is a record of what was believed
at a moment. Overwriting one destroys the evidence the ledger exists to
accumulate. Resolutions are written to a separate table keyed by forecast id;
nothing in the codebase issues an UPDATE against ``forecasts``.

``input_hash`` covers the price series and every parameter, so any forecast can
be regenerated exactly. That is the whole point of the ledger.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utc_column(**kwargs) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), **kwargs)


class Forecast(Base):
    """One distribution, for one ticker, at one horizon, at one moment.

    Never a point target. ``q05..q95`` plus ``(mu, sigma, nu)`` are the
    distribution; there is deliberately no ``expected_price`` column, because a
    column like that is how point targets get reintroduced.
    """

    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = _utc_column(nullable=False, index=True)

    # Point-in-time: when the *data* behind this forecast was true. The CHECK
    # below is the no-lookahead guarantee.
    data_asof: Mapped[datetime] = _utc_column(nullable=False)

    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    spot: Mapped[float] = mapped_column(Float, nullable=False)

    # Distribution parameters. mu and sigma are per-horizon (cumulative), not
    # daily -- the scaling happens before the row is written so that a stored
    # forecast is self-contained and can be resolved without re-deriving.
    mu: Mapped[float] = mapped_column(Float, nullable=False)
    sigma: Mapped[float] = mapped_column(Float, nullable=False)
    nu: Mapped[float] = mapped_column(Float, nullable=False)

    q05: Mapped[float] = mapped_column(Float, nullable=False)
    q25: Mapped[float] = mapped_column(Float, nullable=False)
    q50: Mapped[float] = mapped_column(Float, nullable=False)
    q75: Mapped[float] = mapped_column(Float, nullable=False)
    q95: Mapped[float] = mapped_column(Float, nullable=False)
    p_positive: Mapped[float] = mapped_column(Float, nullable=False)

    # How mu was arrived at: "capm" at <=21d, "capm_shrunk_1y", etc. A short
    # horizon must record "capm" -- non-negotiable 1.
    drift_source: Mapped[str] = mapped_column(String(32), nullable=False)

    # Constraint 3: whether the GARCH fit passed identification, and if not, why
    # it was rejected. A rejection is a normal, reportable outcome.
    garch_identified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    resolve_at: Mapped[datetime] = _utc_column(nullable=False, index=True)

    # Fields the source did not return, carried from Provenance.missing so the
    # UI can surface them against the forecast that was made despite them.
    missing_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    resolution: Mapped["Resolution | None"] = relationship(
        back_populates="forecast", uselist=False
    )

    __table_args__ = (
        # TEST 5. The database, not a code convention.
        CheckConstraint("data_asof <= created_at", name="ck_forecasts_no_lookahead"),
        CheckConstraint("horizon_days > 0", name="ck_forecasts_positive_horizon"),
        CheckConstraint("sigma > 0", name="ck_forecasts_positive_sigma"),
        CheckConstraint("nu >= 2.0", name="ck_forecasts_nu_defined_variance"),
        CheckConstraint("q05 <= q25 AND q25 <= q50 AND q50 <= q75 AND q75 <= q95",
                        name="ck_forecasts_quantiles_ordered"),
        CheckConstraint("p_positive >= 0.0 AND p_positive <= 1.0",
                        name="ck_forecasts_p_positive_is_probability"),
        CheckConstraint("resolve_at > created_at", name="ck_forecasts_resolves_in_future"),
        # A rejected fit must say why; an accepted one must not carry a reason.
        CheckConstraint(
            "(garch_identified = 0 AND rejection_reason IS NOT NULL) OR "
            "(garch_identified = 1 AND rejection_reason IS NULL)",
            name="ck_forecasts_rejection_reason_iff_rejected",
        ),
        Index("ix_forecasts_ticker_horizon", "ticker", "horizon_days"),
    )


class Resolution(Base):
    """What actually happened. Written once, when a forecast matures."""

    __tablename__ = "resolutions"

    forecast_id: Mapped[int] = mapped_column(
        ForeignKey("forecasts.id", ondelete="RESTRICT"), primary_key=True
    )
    resolved_at: Mapped[datetime] = _utc_column(nullable=False)
    actual_price: Mapped[float] = mapped_column(Float, nullable=False)

    # F(realized) under the stored t-distribution. Uniform across many
    # resolutions means calibrated. This is the number test 3 checks.
    pit: Mapped[float] = mapped_column(Float, nullable=False)
    realized_return: Mapped[float] = mapped_column(Float, nullable=False)
    log_score: Mapped[float] = mapped_column(Float, nullable=False)

    forecast: Mapped[Forecast] = relationship(back_populates="resolution")

    __table_args__ = (
        CheckConstraint("pit >= 0.0 AND pit <= 1.0", name="ck_resolutions_pit_is_probability"),
        CheckConstraint("actual_price > 0", name="ck_resolutions_positive_price"),
    )


class ModelVersion(Base):
    """Provenance for the model itself.

    ``validation_evidence`` is what a promotion was justified by. A version
    promoted without evidence is visible as such rather than indistinguishable
    from one that earned it.
    """

    __tablename__ = "model_versions"

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = _utc_column(nullable=False)
    changelog: Mapped[str] = mapped_column(Text, nullable=False)
    promoted_from: Mapped[str | None] = mapped_column(
        ForeignKey("model_versions.version"), nullable=True
    )
    validation_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchRun(Base):
    """A qualitative research pass, kept separate from the quantitative ledger.

    ``epistemic_tags`` records how much each claim is worth -- sourced,
    inferred, speculative. Keeping this out of ``forecasts`` is deliberate:
    narrative never becomes a distribution parameter.
    """

    __tablename__ = "research_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    run_at: Mapped[datetime] = _utc_column(nullable=False)
    claims_json: Mapped[str] = mapped_column(Text, nullable=False)
    sources_json: Mapped[str] = mapped_column(Text, nullable=False)
    epistemic_tags: Mapped[str] = mapped_column(Text, nullable=False)


class ProvenanceRecord(Base):
    """One fetch, kept so a forecast's inputs can be audited after the fact."""

    __tablename__ = "provenance_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    params_json: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = _utc_column(nullable=False)
    data_asof: Mapped[datetime | None] = _utc_column(nullable=True)
    quality: Mapped[str] = mapped_column(String(16), nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    missing_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "data_asof IS NULL OR data_asof <= fetched_at",
            name="ck_provenance_no_lookahead",
        ),
    )


class Account(Base):
    """Stated account total, for the reconciliation gate (test 6)."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    as_of: Mapped[datetime] = _utc_column(nullable=False)
    stated_total: Mapped[float] = mapped_column(Float, nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False)

    # Set by the reconciliation check. Downstream analysis refuses to run when
    # this is False -- an unreconciled book makes every risk number fiction.
    reconciled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reconciliation_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    positions: Mapped[list["Position"]] = relationship(back_populates="account")


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    price_asof: Mapped[datetime] = _utc_column(nullable=False)

    account: Mapped[Account] = relationship(back_populates="positions")

    __table_args__ = (
        UniqueConstraint("account_id", "ticker", name="uq_positions_account_ticker"),
        CheckConstraint("price > 0", name="ck_positions_positive_price"),
    )
