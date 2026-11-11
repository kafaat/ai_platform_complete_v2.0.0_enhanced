"""R09 learning-label integrity: server-side labels (F4), review guard (F7), calibration write
authz (F8) and shared outcome eligibility on prediction calibration (F9).

Pure-function tests plus source-level wiring witnesses (no DB stand-ins).
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from api.learning_feedback import learning_candidate_review_transition
from core.outcome_reconciler import (
    OutcomeLabelConflict,
    find_stored_value,
    recommendation_outcome_write_action,
    reconcile_planned_with_decision,
    reconcile_recommendation_outcome_labels,
)

pytestmark = pytest.mark.unit

API = Path(__file__).resolve().parents[1] / "api"


def _stored(**over):
    row = {
        "field_id": "fld-1",
        "crop": "wheat",
        "recommendation": {"status": "ok", "predicted_yield_t_ha": 4.0},
        "issued_at": datetime.now(UTC) - timedelta(days=150),
        "created_at": None,
    }
    row.update(over)
    return row


def _labels(stored, **over):
    args = {
        "stored": stored,
        "client_predicted": None,
        "client_matured": False,
        "actual": 4.5,
        "crop": "wheat",
        "field_id": "fld-1",
    }
    args.update(over)
    return reconcile_recommendation_outcome_labels(**args)


# ── F4: recommendation outcome labels ────────────────────────────────────────────────


def test_prediction_is_loaded_from_the_stored_recommendation():
    out = _labels(_stored())
    assert out["predicted_yield_t_ha"] == 4.0
    assert out["prediction_source"] == "stored_recommendation"


def test_client_prediction_that_differs_from_stored_is_rejected():
    with pytest.raises(OutcomeLabelConflict) as exc:
        _labels(_stored(), client_predicted=4.5)
    assert exc.value.code == "predicted_yield_mismatch"
    assert exc.value.detail["stored_predicted_yield_t_ha"] == 4.0


def test_matching_client_prediction_is_accepted():
    assert _labels(_stored(), client_predicted=4.0)["predicted_yield_t_ha"] == 4.0


def test_client_cannot_invent_a_prediction_the_stored_recommendation_lacks():
    with pytest.raises(OutcomeLabelConflict):
        _labels(_stored(recommendation={"status": "ok"}), client_predicted=4.5)


def test_stored_json_text_and_nested_prediction_are_read():
    stored = _stored(recommendation='{"log": {"predicted_yield_t_ha": 3.2}}')
    assert _labels(stored)["predicted_yield_t_ha"] == pytest.approx(3.2)
    assert find_stored_value({"a": {"b": {"k": 1}}}, "k") == 1
    assert find_stored_value("not json", "k") is None


def test_field_or_crop_mismatch_with_stored_recommendation_is_rejected():
    with pytest.raises(OutcomeLabelConflict) as exc:
        _labels(_stored(), field_id="other")
    assert exc.value.code == "field_mismatch"
    with pytest.raises(OutcomeLabelConflict) as exc:
        _labels(_stored(), crop="sorghum")
    assert exc.value.code == "crop_mismatch"


def test_maturity_is_derived_from_timestamps_when_possible():
    out = _labels(_stored())
    assert out["matured_within_lag"] is True
    assert out["maturity_source"] == "derived_from_timestamps"


def test_client_maturity_claim_contradicting_timestamps_is_rejected():
    young = _stored(issued_at=datetime.now(UTC) - timedelta(days=10))
    with pytest.raises(OutcomeLabelConflict) as exc:
        _labels(young, client_matured=True)
    assert exc.value.code == "maturity_contradicts_timestamps"
    assert _labels(young)["matured_within_lag"] is False


def test_without_stored_recommendation_client_values_are_flagged_unverified():
    out = _labels(None, client_predicted=4.0, client_matured=True)
    assert out["predicted_yield_t_ha"] == 4.0
    assert out["prediction_source"] == "client_unverified"
    assert out["maturity_source"] == "client_unverified"


def test_duplicate_outcome_for_same_recommendation_replays_not_inserts():
    assert recommendation_outcome_write_action(None, actual_yield_t_ha=4.0) == "insert"
    pending = {"outcome_id": 7, "actual_yield_t_ha": None}
    assert recommendation_outcome_write_action(pending, actual_yield_t_ha=None) == "replay"
    assert recommendation_outcome_write_action(pending, actual_yield_t_ha=4.0) == "complete"
    done = {"outcome_id": 7, "actual_yield_t_ha": 4.0}
    assert recommendation_outcome_write_action(done, actual_yield_t_ha=4.0) == "replay"
    assert recommendation_outcome_write_action(done, actual_yield_t_ha=None) == "replay"
    assert recommendation_outcome_write_action(done, actual_yield_t_ha=5.0) == "conflict"


def test_router_bridge_path_uses_server_labels_and_dedupes_by_recommendation():
    text = (API / "routers/recommendations.py").read_text(encoding="utf-8")
    start = text.index("# Pre-cutover bridge:")
    bridge = text[start : text.index("# مُسجَّل أخيراً عمداً:", start)]
    assert "await _server_outcome_labels(conn, req)" in bridge
    assert "recommendation_outcome_write_action(" in bridge
    assert "pg_advisory_xact_lock" in bridge
    insert = bridge[bridge.index("INSERT INTO recommendation_outcomes") :]
    assert "req.predicted_yield_t_ha" not in insert.split("return", 1)[0]
    assert "req.matured_within_lag" not in insert.split("return", 1)[0]


# ── F4: decision outcome planned values ──────────────────────────────────────────────


def test_planned_values_come_from_stored_decision():
    stored = {"field_id": "fld-1", "decision_value": {"recommended_irrigation_mm": 25.0}}
    planned, sources = reconcile_planned_with_decision(
        stored=stored,
        client_planned={"recommended_irrigation_mm": None, "expected_yield_t_ha": 3.0},
        field_id="fld-1",
    )
    assert planned["recommended_irrigation_mm"] == 25.0
    assert sources["recommended_irrigation_mm"] == "decision_record"
    assert sources["expected_yield_t_ha"] == "client_unverified"


def test_planned_value_differing_from_stored_decision_is_rejected():
    stored = {"field_id": "fld-1", "decision_value": '{"planned": {"predicted_stress_days": 2}}'}
    with pytest.raises(OutcomeLabelConflict) as exc:
        reconcile_planned_with_decision(
            stored=stored, client_planned={"predicted_stress_days": 0}, field_id="fld-1"
        )
    assert exc.value.code == "planned_mismatch"
    planned, _ = reconcile_planned_with_decision(
        stored=stored, client_planned={"predicted_stress_days": None}, field_id="fld-1"
    )
    assert planned["predicted_stress_days"] == 2 and isinstance(
        planned["predicted_stress_days"], int
    )


def test_decision_outcome_route_reconciles_planned_and_keeps_422():
    text = (API / "routers/decision_record.py").read_text(encoding="utf-8")
    body = text[text.index('@router.post("/api/v1/outcome/record")') :]
    body = body[: body.index("@router.get(")]
    assert "reconcile_planned_with_decision(" in body
    assert "except HTTPException:\n        raise" in body  # 422 is not swallowed into 503
    assert "_json.dumps(planned)" in body


# ── F7: review guard ─────────────────────────────────────────────────────────────────


def test_approval_requires_reviewer_and_sets_reviewed_at():
    out = learning_candidate_review_transition("review_ready", "approved", reviewed_by="u-1")
    assert out["status"] == "approved"
    assert out["reviewed_by"] == "u-1"
    assert out["reviewed_at"] is not None
    for blank in (None, "", "   "):
        with pytest.raises(ValueError, match="REVIEWER_REQUIRED"):
            learning_candidate_review_transition("review_ready", "approved", reviewed_by=blank)
    with pytest.raises(ValueError, match="REVIEWER_REQUIRED"):
        learning_candidate_review_transition("blocked", "rejected", reviewed_by=None)


def test_only_review_ready_can_be_approved_and_terminal_states_are_final():
    with pytest.raises(ValueError, match="INVALID_REVIEW_TRANSITION"):
        learning_candidate_review_transition("blocked", "approved", reviewed_by="u-1")
    with pytest.raises(ValueError, match="CANDIDATE_ALREADY_REVIEWED"):
        learning_candidate_review_transition("approved", "rejected", reviewed_by="u-1")
    with pytest.raises(ValueError, match="UNSUPPORTED_REVIEW_STATUS"):
        learning_candidate_review_transition("review_ready", "monitor", reviewed_by="u-1")
    at = datetime(2026, 11, 8, tzinfo=UTC)
    out = learning_candidate_review_transition(
        "monitor", "rejected", reviewed_by="u-2", reviewed_at=at
    )
    assert out["reviewed_at"] == at


# ── F8: calibration write routes require CALIBRATION_RUN ────────────────────────────


def _user_dependency(fn: ast.AsyncFunctionDef) -> str:
    for arg, default in zip(fn.args.args[-len(fn.args.defaults) :], fn.args.defaults, strict=True):
        if arg.arg == "user":
            return ast.unparse(default)
    return ""


def test_calibration_write_routes_require_calibration_run_permission():
    tree = ast.parse((API / "routers/calibration.py").read_text(encoding="utf-8"))
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}
    for name in (
        "apply_region_adaptation_from_evidence",
        "set_region_override",
        "delete_region_override",
    ):
        assert _user_dependency(funcs[name]) == (
            "Depends(require_permission(Permission.CALIBRATION_RUN))"
        ), name


def test_adaptation_apply_audits_previous_override_values():
    text = (API / "routers/calibration.py").read_text(encoding="utf-8")
    body = text[text.index("async def apply_region_adaptation_from_evidence(") :]
    body = body[: body.index("class ProposeValuesRequest")]
    assert "old_values = await _read_override_values(conn, prof.region)" in body
    assert '"adaptation_applied", old_values, accepted' in body
    assert body.index("_read_override_values") < body.index("INSERT INTO calibration_override")


# ── F9: prediction calibration applies the shared outcome eligibility ───────────────


def test_prediction_calibration_filters_through_shared_eligibility():
    text = (API / "routers/learning.py").read_text(encoding="utf-8")
    body = text[text.index("async def prediction_calibration_status(") :]
    assert "recommendation_outcome_eligibility(" in body
    assert "matured_within_lag" in body
    assert '"excluded_reasons"' in body
