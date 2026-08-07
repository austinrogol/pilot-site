"""The rate governor must fail closed.

Every test here is a case where the safe answer and the convenient answer
differ. The governor is required to pick the safe one.
"""
from __future__ import annotations

import datetime as dt

import pytest

from edgeloop.data.governor import Decision, GovernorStateError, RateGovernor

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def make(tmp_path, limit=5, spacing=0.0) -> RateGovernor:
    return RateGovernor(tmp_path / "governor_state.json", limit, spacing)


def test_fresh_deploy_is_permitted(tmp_path):
    governor = make(tmp_path)
    assert governor.evaluate(NOW, []).permitted


def test_naive_datetime_is_refused(tmp_path):
    """An ambiguous clock cannot be reasoned about, so it is not reasoned about."""
    governor = make(tmp_path)
    decision = governor.evaluate(dt.datetime(2026, 8, 7, 12, 0, 0), [])
    assert not decision.permitted
    assert decision.hard_block
    assert "timezone-aware" in decision.reason


def test_unreadable_state_blocks(tmp_path):
    """An unreadable ledger could be hiding real calls."""
    governor = make(tmp_path)
    decision = governor.evaluate(NOW, None)
    assert not decision.permitted
    assert decision.hard_block
    assert "fails closed" in decision.reason


def test_corrupt_state_file_reads_as_none_not_empty(tmp_path):
    """The difference between None and [] is the whole safety property."""
    governor = make(tmp_path)
    governor.state_path.parent.mkdir(parents=True, exist_ok=True)
    governor.state_path.write_text("{not json")
    assert governor.load_history() is None
    assert not governor.evaluate(NOW, governor.load_history()).permitted


def test_wrong_shaped_state_is_corrupt(tmp_path):
    governor = make(tmp_path)
    governor.state_path.parent.mkdir(parents=True, exist_ok=True)
    governor.state_path.write_text('{"calls": [1, 2, 3]}')
    assert governor.load_history() is None


def test_naive_history_entry_blocks(tmp_path):
    governor = make(tmp_path)
    decision = governor.evaluate(NOW, ["2026-08-07T11:00:00"])  # no offset
    assert not decision.permitted
    assert "unparseable or naive" in decision.reason


def test_daily_cap_is_a_hard_block(tmp_path):
    governor = make(tmp_path, limit=3)
    history = [(NOW - dt.timedelta(hours=h)).isoformat() for h in (1, 2, 3)]
    decision = governor.evaluate(NOW, history)
    assert not decision.permitted
    assert decision.hard_block
    assert decision.retry_after_seconds is None
    assert "daily cap" in decision.reason


def test_window_is_trailing_not_calendar(tmp_path):
    """A calendar reset would let 2x the cap through around midnight.

    Three calls 25 hours ago are outside a trailing 24h window and must not
    count; the same three would still be 'yesterday' under a calendar rule at
    some clock offsets.
    """
    governor = make(tmp_path, limit=3)
    history = [(NOW - dt.timedelta(hours=25)).isoformat() for _ in range(3)]
    assert governor.evaluate(NOW, history).permitted


def test_spacing_is_soft_and_reports_retry_after(tmp_path):
    """Spacing delays a call. It must never refuse one -- that is the cap's job."""
    governor = make(tmp_path, limit=100, spacing=10.0)
    history = [(NOW - dt.timedelta(seconds=4)).isoformat()]
    decision = governor.evaluate(NOW, history)
    assert not decision.permitted
    assert not decision.hard_block
    assert decision.retry_after_seconds == pytest.approx(6.0, abs=0.01)


def test_future_timestamps_are_a_hard_block(tmp_path):
    """Clock skew is not a bounded wait, so it is never slept through."""
    governor = make(tmp_path, limit=100, spacing=0.0)
    history = [(NOW + dt.timedelta(hours=2)).isoformat()]
    decision = governor.evaluate(NOW, history)
    assert not decision.permitted
    assert decision.hard_block
    assert "FUTURE" in decision.reason


def test_record_is_durable_and_atomic(tmp_path):
    governor = make(tmp_path)
    governor.record(NOW)
    governor.record(NOW + dt.timedelta(seconds=1))
    assert len(RateGovernor(governor.state_path, 5).load_history()) == 2


def test_record_refuses_to_clobber_corrupt_state(tmp_path):
    """Overwriting would erase the history the cap rides on."""
    governor = make(tmp_path)
    governor.state_path.parent.mkdir(parents=True, exist_ok=True)
    governor.state_path.write_text("{corrupt")
    with pytest.raises(GovernorStateError):
        governor.record(NOW)
    assert governor.state_path.read_text() == "{corrupt"


def test_blocked_check_records_nothing(tmp_path):
    governor = make(tmp_path, limit=1)
    assert governor.check_and_record(NOW).permitted
    before = governor.load_history()
    assert not governor.check_and_record(NOW + dt.timedelta(seconds=1)).permitted
    assert governor.load_history() == before


def test_budget_reports_remaining(tmp_path):
    governor = make(tmp_path, limit=10)
    for i in range(3):
        governor.record(NOW + dt.timedelta(seconds=i))
    budget = governor.budget(NOW + dt.timedelta(minutes=1))
    assert budget == {"readable": True, "used": 3, "limit": 10, "remaining": 7}


def test_decision_is_falsy_when_blocked():
    assert not Decision(False, "no", 0, 1)
    assert Decision(True, "yes", 0, 1)
