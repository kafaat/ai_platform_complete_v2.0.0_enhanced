"""Planned is not executed: status lifecycles and actuals-only aggregation.

Pure/model-level tests (no database) for the farm-operations ledger status contract,
the field-task transition table, the completion fields of ``TaskUpdateRequest``, and the
report helpers that separate executed activities from planned ones.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from api.analytics_shapers import _activities_done, _shape_farm_summary
from api.api_models import (
    TASK_TRANSITIONS,
    TaskUpdateRequest,
    task_allowed_sources,
    task_transition_allowed,
)
from core import farm_operations_ledger as ledger_core
from pydantic import ValidationError

pytestmark = pytest.mark.unit

API = Path(__file__).resolve().parents[1] / "api"
TODAY = date(2026, 11, 8)


# ── farm operations ledger: status is an enum, completed is not in the future ──
@pytest.mark.parametrize("status", ["planned", "in_progress", "completed", "cancelled"])
def test_known_operation_statuses_are_accepted(status):
    assert ledger_core.validate_operation_status(status, TODAY, today=TODAY) == status


@pytest.mark.parametrize("status", ["done", "Completed", "", "finished"])
def test_free_text_operation_status_is_rejected(status):
    with pytest.raises(ValueError, match="status must be one of"):
        ledger_core.validate_operation_status(status, TODAY, today=TODAY)


def test_completed_operation_allows_one_day_of_timezone_skew_only():
    tomorrow = TODAY + timedelta(days=1)
    assert ledger_core.validate_operation_status("completed", tomorrow, today=TODAY)
    with pytest.raises(ValueError, match="future"):
        ledger_core.validate_operation_status("completed", TODAY + timedelta(days=2), today=TODAY)
    # A plan may be dated in the future.
    assert ledger_core.validate_operation_status("planned", TODAY + timedelta(days=30), today=TODAY)


def test_operation_request_model_enforces_the_status_contract():
    from api.routers.farm_operations_ledger import OperationLedgerIn

    base = {"operation_type": "irrigation", "field_id": "f-1"}
    ok = OperationLedgerIn(operation_date=date.today(), **base)
    assert ok.status == "completed"
    planned = OperationLedgerIn(
        operation_date=date.today() + timedelta(days=20), status="planned", **base
    )
    assert planned.status == "planned"
    with pytest.raises(ValidationError):
        OperationLedgerIn(operation_date=date.today(), status="done-ish", **base)
    with pytest.raises(ValidationError):
        OperationLedgerIn(operation_date=date.today() + timedelta(days=20), **base)


def test_actuals_queries_count_only_completed_operations_up_to_today():
    assert ledger_core.ACTUAL_OPERATION_SQL == (
        "status = 'completed' AND operation_date <= CURRENT_DATE"
    )
    core_src = (API.parent / "core/farm_operations_ledger.py").read_text(encoding="utf-8")
    fetch = core_src.split("async def fetch_budget_and_actual", 1)[1]
    assert "AND {ACTUAL_OPERATION_SQL}" in fetch
    router = (API / "routers/farm_operations_ledger.py").read_text(encoding="utf-8")
    # HTTP summary (ops CTE + breakdown) and the season summary (CTE + breakdown).
    assert router.count("{ledger_core.ACTUAL_OPERATION_SQL}") == 4
    assert '"planned_cost": float(row["planned_cost"] or 0.0)' in router
    assert "async def _fetch_budget_and_actual" not in router, (
        "budget/actual fetch moved to core.farm_operations_ledger; a router copy would split the query"
    )


# ── field tasks: transition table ─────────────────────────────────────────────
@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        ("pending", "in_progress", True),
        ("in_progress", "completed", True),
        ("pending", "completed", True),  # the mobile client completes directly
        ("pending", "cancelled", True),
        ("completed", "pending", True),  # reopen (completed_at is cleared by the route)
        ("completed", "cancelled", False),
        ("cancelled", "completed", False),
        ("cancelled", "in_progress", False),
        ("cancelled", "pending", True),
        ("completed", "completed", True),  # honest repeat
        (None, "in_progress", True),  # legacy NULL status behaves as pending
    ],
)
def test_task_transition_table(current, target, allowed):
    assert task_transition_allowed(current, target) is allowed


def test_allowed_sources_are_the_inverse_of_the_table():
    for target in TASK_TRANSITIONS:
        sources = task_allowed_sources(target)
        assert target in sources
        for src in TASK_TRANSITIONS:
            assert (src in sources) == task_transition_allowed(src, target)
    assert "completed" not in task_allowed_sources("cancelled")
    assert task_allowed_sources("completed") == ["completed", "in_progress", "pending"]


# ── TaskUpdateRequest completion fields ──────────────────────────────────────
def test_client_completed_at_within_skew_is_accepted_and_naive_means_utc():
    now = datetime.now(UTC)
    req = TaskUpdateRequest(status="completed", completed_at=now + timedelta(minutes=2))
    assert req.completed_at is not None
    naive = TaskUpdateRequest(status="completed", completed_at=datetime(2026, 1, 2, 3, 4))
    assert naive.completed_at == datetime(2026, 1, 2, 3, 4, tzinfo=UTC)


def test_future_completed_at_is_rejected():
    with pytest.raises(ValidationError, match="future"):
        TaskUpdateRequest(status="completed", completed_at=datetime.now(UTC) + timedelta(hours=1))


@pytest.mark.parametrize(
    "fields",
    [
        {"completed_at": "2026-01-01T00:00:00Z"},
        {"actual_cost_usd": 5},
        {"status": "in_progress", "actual_cost_usd": 5},
    ],
)
def test_completion_fields_require_status_completed(fields):
    with pytest.raises(ValidationError, match="require status=completed"):
        TaskUpdateRequest(**fields)


def test_negative_actual_cost_is_rejected():
    with pytest.raises(ValidationError):
        TaskUpdateRequest(status="completed", actual_cost_usd=-1)


@pytest.mark.parametrize("value", [True, "NaN", "12.345", 100_000_000])
def test_actual_cost_must_fit_the_database_without_rounding(value):
    with pytest.raises(ValidationError):
        TaskUpdateRequest(status="completed", actual_cost_usd=value)


@pytest.mark.parametrize("value", [0, "12.500", 99_999_999.99])
def test_actual_cost_preserves_valid_cents(value):
    assert TaskUpdateRequest(status="completed", actual_cost_usd=value).actual_cost_usd == float(
        value
    )


def test_cost_analytics_defaults_to_completed_and_allows_recorded_costs():
    from inspect import signature

    from api.routers import analytics

    for route in (analytics.analytics_costs, analytics.analytics_costs_by_field):
        assert signature(route).parameters["task_scope"].default == "completed"
    assert analytics._TASK_COST_FILTER == {
        "completed": "actual_cost_usd IS NOT NULL AND status = 'completed'",
        "recorded": "actual_cost_usd IS NOT NULL",
    }


# ── reports: executed activities are counted apart from planned ones ─────────
def test_done_count_ignores_planned_and_skipped():
    assert _activities_done({"planned": 4, "done": 6, "skipped": 2}) == 6
    assert _activities_done({"planned": 4}) == 0
    out = _shape_farm_summary(
        farms_count=1,
        fields_count=1,
        total_area_ha=1,
        active_seasons_count=1,
        activities_by_status={"planned": 4, "done": 6},
        open_alerts_count=0,
        area_by_crop=[],
    )
    assert out["activities_total"] == 10 and out["activities_done_total"] == 6


def test_field_and_season_reports_expose_done_counts():
    src = (API / "routers/reports.py").read_text(encoding="utf-8")
    assert "COUNT(*) FILTER (WHERE status = 'done') AS done_count" in src
    assert '"activities_done_total": _activities_done(by_status)' in src
    assert '"activities_done_count": _activities_done(activities_by_status)' in src
    assert "SELECT COUNT(*) FROM activities WHERE season_id" not in src, (
        "counting every activity mixes planned rows into executed totals"
    )
