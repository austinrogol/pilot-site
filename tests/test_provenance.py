"""Provenance: the missing register and the no-lookahead invariant."""
from __future__ import annotations

import datetime as dt

import pytest

from edgeloop.data.provenance import Provenance, Quality, input_hash

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def make(**kwargs) -> Provenance:
    defaults = dict(
        source="fmp",
        endpoint="quote",
        params={"symbol": "NVDA"},
        fetched_at=NOW,
        data_asof=NOW - dt.timedelta(hours=1),
    )
    return Provenance(**{**defaults, **kwargs})


def test_naive_timestamps_are_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        make(fetched_at=dt.datetime(2026, 8, 7, 12, 0, 0))


def test_data_after_fetch_is_refused():
    """A record cannot know the future. Caught here, before the DB constraint."""
    with pytest.raises(ValueError, match="claims to know the future"):
        make(data_asof=NOW + dt.timedelta(seconds=1))


def test_adding_a_missing_field_downgrades_quality():
    prov = make()
    assert prov.quality is Quality.OK
    prov.add_missing("beta", "source returned null")
    assert prov.quality is Quality.PARTIAL
    assert len(prov.missing) == 1
    assert "quote.beta" in str(prov.missing[0])


def test_missing_does_not_upgrade_a_worse_quality():
    prov = make(quality=Quality.MISSING)
    prov.add_missing("beta", "null")
    assert prov.quality is Quality.MISSING


def test_null_data_asof_is_allowed_and_reported():
    """Some FMP records carry no timestamp. That is null, never 'now'."""
    prov = make(data_asof=None)
    assert prov.data_asof is None
    assert prov.age_seconds is None
    assert "NULL" in prov.render()


def test_render_lists_every_missing_field():
    prov = make()
    prov.add_missing("beta", "null")
    prov.add_missing("averageVolume", "null")
    rendered = prov.render()
    assert "missing[2]" in rendered
    assert "beta" in rendered and "averageVolume" in rendered


def test_to_dict_is_json_safe():
    import json

    prov = make()
    prov.add_missing("beta", "null")
    json.dumps(prov.to_dict())  # must not raise


class TestInputHash:
    """input_hash backs the regenerate-any-forecast-exactly promise."""

    def test_is_order_independent(self):
        assert input_hash({"a": 1, "b": 2}) == input_hash({"b": 2, "a": 1})

    def test_distinguishes_values(self):
        assert input_hash({"a": 1}) != input_hash({"a": 2})

    def test_distinguishes_a_single_changed_price(self):
        base = [("2026-08-07", 223.96), ("2026-08-06", 218.99)]
        bumped = [("2026-08-07", 223.97), ("2026-08-06", 218.99)]
        assert input_hash(base) != input_hash(bumped)

    def test_is_stable_across_calls(self):
        payload = {"symbol": "NVDA", "series": [(1, 2.0), (3, 4.0)]}
        assert input_hash(payload) == input_hash(payload)

    def test_is_hex_sha256(self):
        digest = input_hash({"a": 1})
        assert len(digest) == 64
        int(digest, 16)  # must not raise
