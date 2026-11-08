"""Ledger consumers that take ``ORDER BY ledger_date DESC LIMIT`` must also check age.

``irrigation_state_guard`` declared a 72 h ledger age, but the water twin seeded its initial
depletion from the newest row however old it was, and the field-state projection classified
water stress (and could escalate) from it too. The newest row is not necessarily current.
Both consumers now ask ``water_ledger_row_freshness`` (one constant, imported, not copied);
a row beyond the limit is treated as unavailable and the limitation is declared.
"""

from __future__ import annotations

import ast
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_PLATFORM = _ROOT / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api import irrigation_state_guard as guard  # noqa: E402
from api.canonical_water_stress import stale_ledger_water_stress  # noqa: E402

from shared.contracts.soil import moisture_policy  # noqa: E402

_NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def test_one_ledger_age_constant_everywhere():
    from api import canonical_water_state

    assert guard.DEFAULT_MAX_LEDGER_AGE_HOURS == 72.0
    assert guard.DEFAULT_MAX_LEDGER_AGE_HOURS == moisture_policy.WATER_LEDGER_MAX_AGE_HOURS
    assert canonical_water_state.MAX_LEDGER_AGE_HOURS == guard.DEFAULT_MAX_LEDGER_AGE_HOURS


def test_todays_row_is_current():
    out = guard.water_ledger_row_freshness(date(2026, 11, 8), _NOW)
    assert out == {"current": True, "age_hours": 12.0, "limitation": None, "max_age_hours": 72.0}


def test_iso_string_and_datetime_dates_are_accepted():
    assert guard.water_ledger_row_freshness("2026-11-07", _NOW)["current"] is True
    assert guard.water_ledger_row_freshness(datetime(2026, 11, 7, 5), _NOW)["current"] is True


def test_row_older_than_72h_is_stale():
    out = guard.water_ledger_row_freshness(date(2026, 11, 5), _NOW)  # 84 h
    assert out["current"] is False
    assert out["limitation"] == guard.LIMIT_STALE_WATER_LEDGER == "stale_water_ledger"
    assert out["age_hours"] == pytest.approx(84.0)


def test_boundary_is_inclusive_at_72h():
    now = datetime(2026, 11, 8, 0, 0, tzinfo=UTC)
    assert guard.water_ledger_row_freshness(date(2026, 11, 5), now)["current"] is True
    later = now + timedelta(minutes=1)
    assert guard.water_ledger_row_freshness(date(2026, 11, 5), later)["current"] is False


@pytest.mark.parametrize("bad", [None, "", "not-a-date", 42])
def test_missing_or_invalid_date_is_not_current(bad):
    out = guard.water_ledger_row_freshness(bad, _NOW)
    assert out["current"] is False
    assert out["limitation"] == guard.LIMIT_WATER_LEDGER_DATE_UNPROVEN
    assert out["age_hours"] is None


def test_future_date_proves_nothing():
    out = guard.water_ledger_row_freshness(date(2026, 11, 10), _NOW)
    assert out["current"] is False
    assert out["limitation"] == guard.LIMIT_WATER_LEDGER_DATE_IN_FUTURE


def test_naive_now_is_read_as_utc():
    naive = datetime(2026, 11, 8, 12, 0)
    assert guard.water_ledger_row_freshness(date(2026, 11, 8), naive)["age_hours"] == 12.0


def test_stale_block_carries_no_class_and_no_escalation():
    fr = guard.water_ledger_row_freshness(date(2026, 11, 1), _NOW)
    block = stale_ledger_water_stress(fr)
    assert block["available"] is False
    assert block["water_stress_class"] is None and block["water_stress_awf"] is None
    assert block["escalation_eligible"] is False and block["escalation_triggered"] is False
    assert block["limitations"] == ["stale_water_ledger"]
    assert block["ledger_age_hours"] == fr["age_hours"] > 72
    assert block["max_ledger_age_hours"] == 72.0


def test_water_twin_seed_drops_a_stale_latest_row_and_declares_it():
    from api.water_twin_seed import seed_initial_depletion

    stale = {"ledger_date": "2026-11-01", "depletion_mm": 40.0}
    row, fr, limits = guard.current_ledger_row(stale, _NOW)
    assert row is None and fr["current"] is False
    assert limits == ["stale_water_ledger"]
    # The seeder then sees no ledger row: unavailable, not a week-old depletion as current.
    assert seed_initial_depletion(row, 90.0) == (None, "unavailable")


def test_water_twin_seed_keeps_a_current_latest_row():
    from api.water_twin_seed import seed_initial_depletion

    fresh = {"ledger_date": "2026-11-08", "depletion_mm": 40.0}
    row, fr, limits = guard.current_ledger_row(fresh, _NOW)
    assert row is fresh and fr["current"] is True and limits == []
    assert seed_initial_depletion(row, 90.0) == (40.0, "ledger.depletion_mm")


def test_no_ledger_row_is_an_honest_absence():
    assert guard.current_ledger_row(None, _NOW) == (None, None, [])


def _calls_in(path: Path, name: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    )


@pytest.mark.parametrize(
    "rel",
    ["api/routers/water_twin.py", "api/field_state_projection.py"],
)
def test_latest_row_consumers_check_age(rel):
    """Each ``ORDER BY ledger_date DESC LIMIT`` consumer named in the finding asks the guard."""
    path = _PLATFORM / rel
    text = path.read_text(encoding="utf-8")
    assert "ORDER BY ledger_date DESC LIMIT" in text
    assert (
        _calls_in(path, "water_ledger_row_freshness") + _calls_in(path, "current_ledger_row") >= 1
    )
    assert "DEFAULT_MAX_LEDGER_AGE_HOURS = 72" not in text
    assert "MAX_LEDGER_AGE_HOURS = 72" not in text
