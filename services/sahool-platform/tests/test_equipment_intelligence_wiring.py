"""equipment_intelligence: fail-closed service evaluation + its production consumer.

The core previously defaulted a missing service interval to 250 hours and a missing
last-service meter to 0.0, so an asset with 300 recorded hours and no maintenance record
at all computed 300 - 0 >= 250 and was reported ``due``. The production ``equipment``
table records neither column, so wiring that version would have manufactured a service
claim for every asset on the fleet. These tests pin the repaired contract: missing is
missing, and only absence is absence.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest
from core.equipment_intelligence import (
    STATUS_DUE,
    STATUS_NOT_DUE,
    STATUS_NOT_EVALUATED,
    summarize_equipment,
)

pytestmark = pytest.mark.unit

AS_OF = date(2026, 7, 28)
ROUTER = Path(__file__).resolve().parents[1] / "api" / "routers" / "equipment.py"


def _complete(**overrides):
    asset = {
        "equipment_id": "tractor-1",
        "status": "operational",
        "operating_hours": 300.0,
        "last_service_hours": 0.0,
        "service_interval_hours": 250.0,
    }
    asset.update(overrides)
    return asset


def _only(asset):
    return summarize_equipment(assets=[asset], as_of=AS_OF).to_dict()["assessments"][0]


# ── the regression that motivated the repair ────────────────────────────────
def test_production_payload_never_fabricates_a_service_claim():
    """The exact rows GET /api/v1/equipment returns today must yield zero due assets."""
    production_rows = [
        {"equipment_id": "tractor-1", "status": "operational", "operating_hours": 300.0},
        {"equipment_id": "pump-1", "status": "operational", "operating_hours": 40.0},
    ]
    state = summarize_equipment(assets=production_rows, as_of=AS_OF).to_dict()
    assert state["service_due"] == 0
    assert state["due_asset_ids"] == []
    assert state["service_not_evaluated"] == 2
    assert state["readiness"] == "unknown"


# ── missing input never produces a verdict ──────────────────────────────────
@pytest.mark.parametrize(
    "missing,constraint",
    [
        ("service_interval_hours", "maintenance_policy_missing"),
        ("last_service_hours", "service_meter_baseline_missing"),
        ("operating_hours", "current_meter_reading_missing"),
    ],
)
def test_each_missing_input_blocks_evaluation_and_names_itself(missing, constraint):
    asset = _complete()
    asset.pop(missing)
    assessment = _only(asset)
    assert assessment["status"] == STATUS_NOT_EVALUATED
    assert constraint in assessment["constraints"]
    # The forbidden outcomes, explicitly:
    assert assessment["status"] != STATUS_DUE
    assert assessment["overdue_hours"] is None


def test_missing_policy_does_not_silently_become_not_due():
    """not_evaluated must not collapse into not_due — absence is not a clean bill."""
    assessment = _only(_complete(service_interval_hours=None))
    assert assessment["status"] == STATUS_NOT_EVALUATED
    assert assessment["status"] != STATUS_NOT_DUE


# ── a real zero is a real reading ───────────────────────────────────────────
def test_zero_baseline_is_a_reading_not_an_absence():
    assessment = _only(_complete(operating_hours=0.0, last_service_hours=0.0))
    assert assessment["status"] == STATUS_NOT_DUE
    assert assessment["constraints"] == []


def test_zero_interval_is_a_reading_not_an_absence():
    """interval 0 means 'always due' — a policy, not a missing policy."""
    assessment = _only(_complete(service_interval_hours=0.0))
    assert assessment["status"] == STATUS_DUE


def test_boolean_is_never_accepted_as_a_meter_reading():
    assessment = _only(_complete(operating_hours=True))
    assert assessment["status"] == STATUS_NOT_EVALUATED
    assert "current_meter_reading_missing" in assessment["constraints"]


# ── complete inputs evaluate normally ───────────────────────────────────────
def test_complete_inputs_over_interval_are_due_with_computed_overdue():
    assessment = _only(_complete(operating_hours=300.0))
    assert assessment["status"] == STATUS_DUE
    assert assessment["overdue_hours"] == 50.0


def test_complete_inputs_under_interval_are_not_due():
    assessment = _only(_complete(operating_hours=100.0))
    assert assessment["status"] == STATUS_NOT_DUE
    assert assessment["overdue_hours"] is None


def test_recorded_schedule_that_arrived_is_due_without_meter_inputs():
    """A scheduled date is recorded data, so it stands alone — no assumption involved."""
    assessment = _only({"equipment_id": "pump-1", "next_service_date": "2026-07-01"})
    assert assessment["status"] == STATUS_DUE
    assert assessment["overdue_hours"] is None


def test_unevaluated_fleet_is_unknown_with_zero_coverage():
    """Absence of evidence is reported as unknown — never as ready, never as degraded."""
    state = summarize_equipment(
        assets=[{"equipment_id": "a", "status": "operational", "operating_hours": 10.0}],
        as_of=AS_OF,
    ).to_dict()
    assert state["readiness"] == "unknown"
    assert state["assessment_coverage"] == 0.0
    assert "all_assets_not_evaluated" in state["limitations"]


def test_readiness_vocabulary_keeps_each_state_meaning_one_thing():
    """degraded is reserved for evidenced degradation; a due asset is attention_required."""
    due_asset = _complete(operating_hours=600.0)
    broken_asset = {
        "equipment_id": "b",
        "status": "broken",
        "operating_hours": 10.0,
        "last_service_hours": 0.0,
        "service_interval_hours": 250.0,
    }
    healthy = _complete(operating_hours=10.0)

    assert summarize_equipment(assets=[due_asset], as_of=AS_OF).to_dict()["readiness"] == (
        "attention_required"
    )
    assert summarize_equipment(assets=[broken_asset], as_of=AS_OF).to_dict()["readiness"] == (
        "degraded"
    )
    assert summarize_equipment(assets=[healthy], as_of=AS_OF).to_dict()["readiness"] == "ready"


def test_a_due_asset_outranks_a_degradation_signal():
    """An actionable due must not be hidden behind a degraded verdict."""
    state = summarize_equipment(
        assets=[
            _complete(operating_hours=600.0),
            {
                "equipment_id": "b",
                "status": "broken",
                "operating_hours": 10.0,
                "last_service_hours": 0.0,
                "service_interval_hours": 250.0,
            },
        ],
        as_of=AS_OF,
    ).to_dict()
    assert state["readiness"] == "attention_required"


# ── the production consumer ─────────────────────────────────────────────────
def test_router_consumes_the_core_and_adds_no_route():
    """The consumer is real, and folded into the existing route rather than a new one."""
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "core.equipment_intelligence"
        for alias in node.names
    }
    assert "summarize_equipment" in imports, "router must consume the core"

    routes = [
        d.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for d in node.decorator_list
        if isinstance(d, ast.Call)
        and isinstance(d.func, ast.Attribute)
        and d.args
        and isinstance(d.args[0], ast.Constant)
    ]
    assert sorted(routes) == [
        "/api/v1/equipment",
        "/api/v1/equipment",
        "/api/v1/equipment/{equipment_id}/maintenance",
        "/api/v1/equipment/{equipment_id}/maintenance",
    ], "no route may be added; the summary folds into GET /api/v1/equipment"


def test_consumer_does_not_convert_not_evaluated_into_not_due():
    """The router hands assets straight through; it must not launder the verdict."""
    source = ROUTER.read_text(encoding="utf-8")
    assert "summarize_equipment(assets=assets)" in source
    for laundering in ("not_due", "service_interval_hours=", "last_service_hours="):
        assert laundering not in source, f"router must not inject {laundering!r}"


def _executable_source(path: Path) -> str:
    """Source with docstrings blanked, so prose mentioning a field never false-trips.

    Mirrors scripts/ci/consumer_contract_gate.py — a module is allowed to *describe* the
    service-due inputs in its docstring; it is not allowed to *implement* the rule.
    """
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body[0].value.value = ""
    return ast.unparse(tree)


def test_no_duplicate_service_due_implementation_outside_the_core():
    """Ownership: the service-due rule is implemented in exactly one module."""
    platform = Path(__file__).resolve().parents[1]
    owners = set()
    for path in list((platform / "api").rglob("*.py")) + list((platform / "core").rglob("*.py")):
        if path.name == "equipment_intelligence.py":
            continue
        try:
            source = _executable_source(path)
        except (OSError, SyntaxError):
            continue
        if "service_interval_hours" in source or "last_service_hours" in source:
            owners.add(path.relative_to(platform).as_posix())
    assert owners == set(), f"duplicate service-due logic found in {sorted(owners)}"


def test_future_schedule_does_not_mask_a_meter_overdue():
    """A scheduled date that has NOT arrived must not end the evaluation.

    An owner-supplied implementation of this same slice returned on the first sight of
    ``next_service_date`` and answered ``not_due`` whenever the date was in the future.
    An asset 350 hours past its interval with a service booked five months out then came
    back ``not_due``, and the fleet reported ``ready``.

    That is the original fabrication defect inverted: instead of inventing a due, it hides
    a real one. The rule holds in both directions — a recorded date may establish due when
    it arrives, but it may never overrule the meter.
    """
    assessment = _only(
        _complete(operating_hours=600.0, last_service_hours=0.0, service_interval_hours=250.0)
        | {"next_service_date": "2026-12-31"}
    )
    assert assessment["status"] == STATUS_DUE
    assert assessment["overdue_hours"] == 350.0


def test_future_schedule_with_unevaluable_meter_is_not_due_by_date():
    """A recorded future schedule is real evidence, so it stands when the meter cannot.

    The verdict is not_due *by date*, and ``basis`` says so — it must never be mistaken
    for a not_due the meter corroborated. The constraints name the shortfall explicitly.
    """
    assessment = _only({"equipment_id": "p1", "next_service_date": "2026-12-31"})
    assert assessment["status"] == STATUS_NOT_DUE
    assert assessment["basis"] == "next_service_date"
    assert "service_meter_not_evaluable" in assessment["constraints"]
    assert "maintenance_policy_missing" in assessment["constraints"]


def test_not_due_by_date_is_distinguishable_from_not_due_by_meter():
    """The whole point of ``basis``: two not_due verdicts of very different strength."""
    by_date = _only({"equipment_id": "p1", "next_service_date": "2026-12-31"})
    by_meter = _only(_complete(operating_hours=100.0))
    assert by_date["status"] == by_meter["status"] == STATUS_NOT_DUE
    assert by_date["basis"] != by_meter["basis"]
    assert by_meter["constraints"] == []


def test_no_date_and_unevaluable_meter_stays_not_evaluated():
    """Without any evidence source there is no verdict to give."""
    assessment = _only({"equipment_id": "q1", "status": "operational", "operating_hours": 300.0})
    assert assessment["status"] == STATUS_NOT_EVALUATED
    assert assessment["basis"] is None
