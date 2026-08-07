"""Schema invariants enforced by the database, not by convention.

This file contains **spec test 5** (no lookahead). The spec is explicit that it
must be a database constraint rather than a code convention, so every test here
goes through a real engine and asserts on an IntegrityError from the driver.

The ledger write path is phase 3; the constraint is phase 1 because it belongs
to the schema, and a constraint added after rows exist is a constraint that has
already been violated.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.exc import IntegrityError

from edgeloop.data.db import create_all, session_factory
from edgeloop.data.models import Forecast, Resolution
from sqlalchemy import create_engine

UTC = dt.timezone.utc
CREATED = dt.datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.sqlite'}", future=True)
    create_all(engine)
    with session_factory(engine)() as s:
        yield s


def forecast(**overrides) -> Forecast:
    base = dict(
        created_at=CREATED,
        data_asof=CREATED - dt.timedelta(hours=1),
        ticker="NVDA",
        horizon_days=21,
        model_version="test",
        input_hash="deadbeef",
        spot=223.96,
        mu=0.001,
        sigma=0.12,
        nu=6.0,
        q05=190.0, q25=210.0, q50=224.0, q75=238.0, q95=260.0,
        p_positive=0.51,
        drift_source="capm",
        garch_identified=True,
        rejection_reason=None,
        resolve_at=CREATED + dt.timedelta(days=21),
    )
    return Forecast(**{**base, **overrides})


class TestNoLookahead:
    """SPEC TEST 5."""

    def test_a_valid_forecast_is_accepted(self, session):
        session.add(forecast())
        session.commit()
        assert session.query(Forecast).count() == 1

    def test_data_asof_after_created_at_is_rejected_by_the_database(self, session):
        session.add(forecast(data_asof=CREATED + dt.timedelta(seconds=1)))
        with pytest.raises(IntegrityError, match="ck_forecasts_no_lookahead"):
            session.commit()

    def test_data_asof_equal_to_created_at_is_allowed(self, session):
        """A forecast made the instant its data landed is legitimate."""
        session.add(forecast(data_asof=CREATED))
        session.commit()
        assert session.query(Forecast).count() == 1

    def test_the_constraint_survives_a_raw_insert(self, session):
        """Bypassing the ORM must not bypass the guarantee."""
        from sqlalchemy import text

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO forecasts (created_at, data_asof, ticker, horizon_days, "
                    "model_version, input_hash, spot, mu, sigma, nu, q05, q25, q50, q75, "
                    "q95, p_positive, drift_source, garch_identified, resolve_at) VALUES "
                    "('2026-08-07 12:00:00', '2026-08-08 12:00:00', 'NVDA', 21, 't', 'h', "
                    "1, 0, 1, 6, 1, 2, 3, 4, 5, 0.5, 'capm', 1, '2026-08-28 12:00:00')"
                )
            )
            session.commit()


class TestDistributionIntegrity:
    """Non-negotiable 2: a forecast is a distribution, never a point."""

    def test_there_is_no_expected_price_column(self):
        """A column like that is how point targets get reintroduced."""
        columns = set(Forecast.__table__.columns.keys())
        for banned in ("expected_price", "target_price", "price_target", "point_estimate"):
            assert banned not in columns

    def test_the_quantile_set_is_present(self):
        columns = set(Forecast.__table__.columns.keys())
        assert {"q05", "q25", "q50", "q75", "q95", "mu", "sigma", "nu"} <= columns

    def test_out_of_order_quantiles_are_rejected(self, session):
        session.add(forecast(q50=100.0, q75=90.0))
        with pytest.raises(IntegrityError, match="quantiles_ordered"):
            session.commit()

    def test_p_positive_outside_zero_one_is_rejected(self, session):
        session.add(forecast(p_positive=1.4))
        with pytest.raises(IntegrityError, match="p_positive_is_probability"):
            session.commit()

    def test_nonpositive_sigma_is_rejected(self, session):
        session.add(forecast(sigma=0.0))
        with pytest.raises(IntegrityError, match="positive_sigma"):
            session.commit()


class TestGarchIdentificationRecord:
    """Non-negotiable 3: a rejected fit must say why."""

    def test_rejected_fit_without_a_reason_is_refused(self, session):
        session.add(forecast(garch_identified=False, rejection_reason=None))
        with pytest.raises(IntegrityError, match="rejection_reason_iff_rejected"):
            session.commit()

    def test_rejected_fit_with_a_reason_is_stored(self, session):
        session.add(
            forecast(
                garch_identified=False,
                rejection_reason="n=47 < 150; alpha t-stat 0.9 below threshold",
            )
        )
        session.commit()
        assert session.query(Forecast).one().garch_identified is False

    def test_accepted_fit_carrying_a_reason_is_refused(self, session):
        session.add(forecast(garch_identified=True, rejection_reason="spurious"))
        with pytest.raises(IntegrityError, match="rejection_reason_iff_rejected"):
            session.commit()


class TestResolutionIntegrity:
    def test_pit_must_be_a_probability(self, session):
        session.add(forecast())
        session.commit()
        fid = session.query(Forecast).one().id
        session.add(
            Resolution(
                forecast_id=fid,
                resolved_at=CREATED + dt.timedelta(days=21),
                actual_price=230.0,
                pit=1.3,
                realized_return=0.02,
                log_score=-1.0,
            )
        )
        with pytest.raises(IntegrityError, match="pit_is_probability"):
            session.commit()

    def test_resolution_requires_an_existing_forecast(self, session):
        """Foreign keys are OFF by default in SQLite; db.py turns them on."""
        from edgeloop.data.db import create_db_engine
        from edgeloop.config import Settings

        session.add(
            Resolution(
                forecast_id=9999,
                resolved_at=CREATED,
                actual_price=1.0,
                pit=0.5,
                realized_return=0.0,
                log_score=0.0,
            )
        )
        # Without PRAGMA foreign_keys=ON this would silently succeed.
        with pytest.raises(IntegrityError):
            session.commit()


class TestHorizonSanity:
    def test_resolve_at_must_be_after_created_at(self, session):
        session.add(forecast(resolve_at=CREATED - dt.timedelta(days=1)))
        with pytest.raises(IntegrityError, match="resolves_in_future"):
            session.commit()

    def test_nonpositive_horizon_is_rejected(self, session):
        session.add(forecast(horizon_days=0))
        with pytest.raises(IntegrityError, match="positive_horizon"):
            session.commit()
