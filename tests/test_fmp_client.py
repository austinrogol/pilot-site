"""The FMP client, end to end against recorded bodies.

These run the full path -- cache, governor, transport, parsing, provenance --
without a network route or an API key, which is exactly how phase 1 was
developed.
"""
from __future__ import annotations

import datetime as dt

import pytest

from edgeloop.config import REPO_ROOT, FmpConfig, Settings
from edgeloop.data import endpoints as ep
from edgeloop.data.fmp import FmpClient, FmpError, RateLimited
from edgeloop.data.governor import RateGovernor
from edgeloop.data.provenance import Quality
from edgeloop.data.transport import FixtureTransport, redact

FIXTURES = REPO_ROOT / "fixtures"
UTC = dt.timezone.utc


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        fmp=FmpConfig(api_key=None, max_calls_per_day=500, min_seconds_between_calls=0.0),
        cache_dir=tmp_path / "cache",
        governor_state_path=tmp_path / "governor_state.json",
        database_url=f"sqlite:///{tmp_path / 'test.sqlite'}",
    )


@pytest.fixture
def client(settings) -> FmpClient:
    return FmpClient.from_fixtures(FIXTURES, settings=settings)


class TestParsing:
    async def test_quote_parses_real_body(self, client):
        result = await client.quote("NVDA")
        quote = result.require_first()
        assert quote.symbol == "NVDA"
        assert quote.price == 223.96
        assert result.provenance.quality is Quality.OK
        # timestamp -> data_asof, not the fetch time
        assert result.provenance.data_asof == dt.datetime.fromtimestamp(1786132800, tz=UTC)

    async def test_price_history_close_is_named_price(self, client):
        result = await client.price_history("NVDA")
        assert len(result.rows) == 256
        assert result.rows[0].price == 223.96
        # newest first, as FMP returns it
        assert result.rows[0].date > result.rows[-1].date

    async def test_profile_carries_the_two_load_bearing_fields(self, client):
        profile = (await client.profile("NVDA")).require_first()
        assert profile.beta == 2.211           # CAPM drift
        assert profile.averageVolume == 154610000  # liquidity/exit-capacity sizing

    async def test_peers_market_cap_is_mktcap_here(self, client):
        peers = await client.peers("NVDA")
        assert len(peers.rows) == 9
        assert peers.rows[0].mktCap is not None

    async def test_extra_fields_do_not_break_parsing(self, client):
        """FMP adds columns without warning; a new one must not 500 the service."""
        result = await client.profile("NVDA")
        assert result.provenance.quality in (Quality.OK, Quality.PARTIAL)
        assert result.first is not None


class TestPointInTime:
    async def test_income_statement_asof_is_acceptance_not_period_end(self, client):
        statement = (await client.income_statement("NVDA")).require_first()
        assert statement.date == dt.date(2026, 1, 25)          # fiscal period end
        assert statement.filingDate == dt.date(2026, 2, 25)    # when the world knew
        assert statement.as_of().date() == dt.date(2026, 2, 25)

    async def test_asof_never_silently_falls_back_to_period_end(self):
        """With no acceptance and no filing date, as_of is None -- not `date`.

        Falling back to the period end would manufacture a month of lookahead.
        """
        from edgeloop.data.schemas import IncomeStatement

        bare = IncomeStatement(symbol="X", date=dt.date(2026, 1, 25))
        assert bare.as_of() is None

    async def test_provenance_never_defaults_asof_to_now(self, client):
        """profile has no timestamp; that must surface as missing, not as 'now'."""
        result = await client.profile("NVDA")
        assert result.provenance.data_asof is None
        assert result.provenance.quality is Quality.PARTIAL
        assert any("data_asof" in str(m) for m in result.provenance.missing)


class TestMissingRegister:
    async def test_declared_null_fields_are_registered(self, client, tmp_path):
        """A null in a field we depend on becomes a visible missing[] entry."""
        (tmp_path / "fx").mkdir()
        (tmp_path / "fx" / "profile.json").write_text(
            '[{"symbol":"NVDA","beta":null,"averageVolume":null,"marketCap":1}]'
        )
        client._transport = FixtureTransport(tmp_path / "fx")
        result = await client.profile("NVDA")
        paths = {m.path for m in result.provenance.missing}
        assert "beta" in paths
        assert "averageVolume" in paths
        assert result.provenance.quality is Quality.PARTIAL

    async def test_error_message_body_yields_zero_rows_not_a_default(self, client, tmp_path):
        (tmp_path / "fx").mkdir()
        (tmp_path / "fx" / "quote.json").write_text('{"Error Message": "Invalid API KEY."}')
        client._transport = FixtureTransport(tmp_path / "fx")
        result = await client.quote("NVDA")
        assert result.rows == []
        assert result.provenance.quality is Quality.MISSING

    async def test_require_first_refuses_to_invent_a_row(self, client, tmp_path):
        (tmp_path / "fx").mkdir()
        (tmp_path / "fx" / "quote.json").write_text("[]")
        client._transport = FixtureTransport(tmp_path / "fx")
        result = await client.quote("NVDA")
        with pytest.raises(FmpError, match="refusing to substitute a default"):
            result.require_first()


class TestCacheAndBudget:
    async def test_second_identical_call_is_served_from_cache(self, client):
        await client.quote("NVDA")
        await client.quote("NVDA")
        assert client.budget.uncached == 1
        assert client.budget.cached == 1

    async def test_single_ticker_analysis_stays_under_eight_uncached_calls(self, client):
        """The spec's budget, measured rather than asserted."""
        async with client:
            await client.quote("NVDA")
            await client.price_history("NVDA")
            await client.profile("NVDA")
            await client.key_metrics_ttm("NVDA")
            await client.income_statement("NVDA")
            await client.treasury_rates()
            await client.market_risk_premium()
        assert client.budget.uncached < 8

    async def test_cached_call_does_not_consume_governor_budget(self, client):
        await client.quote("NVDA")
        used_after_first = client.governor.budget(dt.datetime.now(UTC))["used"]
        await client.quote("NVDA")
        assert client.governor.budget(dt.datetime.now(UTC))["used"] == used_after_first


class TestGovernorIntegration:
    async def test_hard_block_with_no_cache_raises(self, settings):
        settings = Settings(
            fmp=FmpConfig(max_calls_per_day=1, min_seconds_between_calls=0.0),
            cache_dir=settings.cache_dir,
            governor_state_path=settings.governor_state_path,
        )
        client = FmpClient.from_fixtures(FIXTURES, settings=settings)
        await client.quote("NVDA")
        with pytest.raises(RateLimited):
            await client.profile("NVDA")

    async def test_expired_cache_is_served_stale_rather_than_failing(self, settings):
        """Labelled, not silent. Constraint 5 forbids silent carry-forward."""
        client = FmpClient.from_fixtures(FIXTURES, settings=settings)
        await client.quote("NVDA")

        # Force the entry to look expired, then spend the budget.
        entry_key = client.cache.build_key(
            "quote", {"symbol": "NVDA"}, dt.datetime.now(UTC).date().isoformat()
        )
        cached = client.cache.get(entry_key)
        client.cache.put(
            entry_key, "quote", {"symbol": "NVDA"}, cached.body,
            ttl_seconds=0, now=dt.datetime.now(UTC) - dt.timedelta(hours=5),
        )
        client.governor.max_calls_per_day = 1  # already spent one

        result = await client.quote("NVDA")
        assert result.provenance.quality is Quality.STALE
        assert "rate governor refused" in result.provenance.note
        assert client.budget.stale_served == 1


class TestBlockedEndpoints:
    def test_requesting_gated_data_raises_rather_than_returning_empty(self):
        with pytest.raises(ep.EndpointBlocked, match="not available on this FMP plan"):
            ep.get("technical_indicators")

    @pytest.mark.parametrize(
        "key", ["technical_indicators", "earnings_transcripts", "form_13f", "cot", "esg", "tipranks"]
    )
    def test_every_blocked_endpoint_stays_visible_in_the_registry(self, key):
        """Deleted gaps get re-proposed; annotated ones do not."""
        assert key in ep.REGISTRY
        assert ep.REGISTRY[key].blocked

    def test_there_is_no_options_endpoint_at_all(self):
        assert not any("option" in k for k in ep.REGISTRY)
        assert "no options data at any tier" in ep.OPTIONS_AVAILABILITY


class TestSecrets:
    def test_api_key_never_appears_in_a_redacted_url(self):
        url = "https://financialmodelingprep.com/stable/quote?symbol=NVDA&apikey=SEKRIT"
        assert "SEKRIT" not in redact(url, "SEKRIT")
        assert "<FMP_API_KEY>" in redact(url, "SEKRIT")

    def test_settings_redaction_hides_the_key(self):
        settings = Settings(fmp=FmpConfig(api_key="SEKRIT"))
        assert "SEKRIT" not in str(settings.redacted())
        assert settings.redacted()["fmp"]["api_key"] == "<set>"

    def test_database_password_is_redacted(self):
        settings = Settings(database_url="postgresql://user:hunter2@host:5432/db")
        assert "hunter2" not in settings.redacted()["database_url"]

    async def test_api_key_is_absent_from_provenance(self, client):
        result = await client.quote("NVDA")
        assert "apikey" not in str(result.provenance.to_dict())

    async def test_missing_key_gives_an_actionable_error(self):
        client = FmpClient(settings=Settings(fmp=FmpConfig(api_key=None)))
        with pytest.raises(FmpError, match="never be written into the repo"):
            _ = client.transport


class TestRegistryIntegrity:
    async def test_required_params_are_enforced_before_any_call(self, client):
        from edgeloop.data.schemas import Quote

        with pytest.raises(FmpError, match="requires"):
            await client.fetch("quote", Quote, {})

    def test_every_working_endpoint_has_a_reachable_url(self):
        for endpoint in ep.REGISTRY.values():
            assert endpoint.url.startswith("https://financialmodelingprep.com/stable/")

    def test_unverified_paths_are_reported_not_hidden(self):
        """The registry must be able to say what it guessed at."""
        unverified = ep.unverified_paths()
        assert unverified, "phase 1 had no live route; these cannot all be verified"
        assert all(e.path_status is ep.PathStatus.INFERRED for e in unverified)

    def test_fixture_backed_endpoints_are_marked_shape_live(self):
        for key in (
            "quote", "historical_price_light", "historical_price_full", "profile",
            "peers", "key_metrics_ttm", "income_statement",
            "price_target_consensus", "treasury_rates", "market_risk_premium",
        ):
            assert ep.REGISTRY[key].shape_status is ep.ShapeStatus.LIVE


class TestMarketRiskPremium:
    async def test_country_filter_happens_client_side(self, client):
        result = await client.market_risk_premium("United States")
        assert len(result.rows) == 1
        assert result.rows[0].country == "United States"
        assert "not honoured" in result.provenance.note

    async def test_absent_country_is_recorded_as_missing(self, client):
        result = await client.market_risk_premium("Atlantis")
        assert result.rows == []
        assert any("Atlantis" in str(m) for m in result.provenance.missing)
