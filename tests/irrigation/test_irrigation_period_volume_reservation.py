from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "services/sahool-platform/api/irrigation_capacity_reservation.py"
SPEC = importlib.util.spec_from_file_location("period_volume_kernel", PATH)
assert SPEC and SPEC.loader
k = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = k
SPEC.loader.exec_module(k)

START = datetime(2026, 11, 27, tzinfo=UTC)
HOUR = timedelta(hours=1)


def admit(cap, *, budget, windows=(), start=START, end=START + HOUR, flow="1500"):
    return k.evaluate_admission(
        policy=k.ResourcePolicy.SHARED_CAPACITY,
        existing=windows,
        requested_start=start,
        requested_end=end,
        requested_flow_m3h=Decimal(flow),
        derated_capacity_m3h=Decimal(cap),
        period_volume_budget=k.PeriodVolumeBudget(
            START, START + 24 * HOUR, Decimal(budget), "synthetic-budget-v1"
        ),
    )


def window(start, end, flow):
    return k.ReservationWindow(start, end, Decimal(flow))


def test_nonoverlapping_pivots_share_period_volume():
    prior = window(START, START + HOUR, "1500")
    result = admit("2000", budget="2500", windows=[prior], start=START + HOUR, end=START + 2 * HOUR)
    assert result.peak_existing_flow_m3h == 0
    assert not result.eligible and result.blocking_code == "PERIOD_VOLUME_EXCEEDED"


def test_exact_budget_accepts_both_pivots():
    prior = window(START, START + HOUR, "1500")
    assert admit(
        "2000", budget="3000", windows=[prior], start=START + HOUR, end=START + 2 * HOUR
    ).eligible


def test_flow_limit_remains_independent():
    prior = window(START, START + HOUR, "1500")
    result = admit("2000", budget="3000", windows=[prior])
    assert not result.eligible and result.blocking_code == "CONCURRENT_LOAD_EXCEEDED"


def test_clip_reservation_at_period_boundary():
    prior = window(START - HOUR, START + HOUR, "1000")
    assert admit(
        "2000", budget="2500", windows=[prior], start=START + HOUR, end=START + 2 * HOUR
    ).eligible
    assert not admit(
        "2000", budget="2499.9999", windows=[prior], start=START + HOUR, end=START + 2 * HOUR
    ).eligible


def test_outside_period_fails_closed():
    result = admit("2000", budget="3000", start=START + 23 * HOUR, end=START + 25 * HOUR)
    assert not result.eligible and result.blocking_code == "REQUEST_OUTSIDE_VOLUME_PERIOD"


def test_stored_precision_cannot_round_up_after_admission():
    with pytest.raises(ValueError, match="PERIOD_VOLUME_FLOW_NOT_STORABLE"):
        admit("2000", budget="3000", flow="1500.00001")


def test_microsecond_accounting_is_exact():
    end = START + timedelta(microseconds=1)
    assert admit("3600", budget="0.000001", end=end, flow="3600").eligible
    assert not admit("3600", budget="0.000000999999", end=end, flow="3600").eligible


def test_no_budget_legacy_behavior():
    assert k.evaluate_admission(
        policy=k.ResourcePolicy.SHARED_CAPACITY,
        existing=[],
        requested_start=START,
        requested_end=START + HOUR,
        requested_flow_m3h=Decimal("1500"),
        derated_capacity_m3h=Decimal("2000"),
    ).eligible
