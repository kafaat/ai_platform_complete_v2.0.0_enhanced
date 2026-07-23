from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "sahool-platform"))

from core.agronomic_state_engine import CanonicalFieldState  # noqa: E402

from shared.field_runtime_cohesion import (  # noqa: E402
    apply_lifecycle_transition,
    build_outcome_feedback,
    build_unified_digital_twin_view,
    create_canonical_state_envelope,
    open_recommendation_lifecycle,
    run_cohesive_field_runtime,
)


def _state() -> CanonicalFieldState:
    return CanonicalFieldState(
        field_id="field-1",
        tenant_id="tenant-1",
        farm_id="farm-1",
        generated_at="2026-06-26T00:00:00+00:00",
        operational_truths={
            "effective_status": "salinity_limited",
            "crop_vigor": 0.72,
            "salinity_class": "critical",
            "kc": 1.05,
            "etc_mm": 6.1,
            "growth_stage": "mid",
        },
        confidence="medium",
        missing_signals=["equipment"],
    )


def test_canonical_state_envelope_is_stable_source_of_truth():
    env1 = create_canonical_state_envelope(_state())
    env2 = create_canonical_state_envelope(_state())
    assert env1["state_id"] == env2["state_id"]
    assert env1["derived_view_policy"] == "canonical_field_state_is_source_of_truth"
    assert env1["tenant_id"] == "tenant-1"


def test_unified_twin_view_is_derived_from_canonical_state():
    env = create_canonical_state_envelope(_state())
    twin = build_unified_digital_twin_view(env, economics={"profit_per_ha": 200})
    assert twin["source_state_id"] == env["state_id"]
    assert twin["health"]["effective_status"] == "salinity_limited"
    assert twin["water"]["etc_mm"] == 6.1
    assert "equipment" in twin["limitations"]


def test_recommendation_lifecycle_blocks_unapproved_actionable_decision():
    env = create_canonical_state_envelope(_state())
    rec = open_recommendation_lifecycle(
        env,
        {
            "actionable": True,
            "executable": False,
            "dispatch_block_reason": "governance_not_evaluated",
            "action_type": "soil_remediation",
        },
    )
    assert rec["status"] == "guardrails_blocked"
    assert rec["source_state_id"] == env["state_id"]


def test_recommendation_lifecycle_closed_loop_feedback():
    env = create_canonical_state_envelope(_state())
    rec = open_recommendation_lifecycle(
        env, {"actionable": True, "executable": True, "action_type": "irrigation"}
    )
    assert rec["status"] == "approved"
    rec = apply_lifecycle_transition(rec, "dispatched", actor="scheduler")
    rec = apply_lifecycle_transition(rec, "executed", actor="pivot-controller")
    rec = apply_lifecycle_transition(
        rec, "verified", actor="field-verifier", evidence={"water_mm": 18}
    )
    feedback = build_outcome_feedback(
        rec, verification={"ok": True}, outcome_metrics={"ndvi_delta": 0.04}
    )
    assert feedback["feature_store_candidate"] is True
    assert feedback["source_state_id"] == env["state_id"]


def test_cohesive_runtime_payload_integrates_existing_coordinator_result_shape():
    class Result:
        canonical_state = _state()
        policy_decision = {
            "actionable": True,
            "executable": True,
            "action_type": "soil_remediation",
        }

    payload = run_cohesive_field_runtime(
        field_intelligence_result=Result(), economics={"profit_per_ha": 100}
    )
    assert payload["contract"] == "canonical_state_to_twin_to_recommendation_to_feedback"
    assert payload["digital_twin_view"]["source_state_id"] == payload["canonical_state"]["state_id"]
    assert payload["recommendation_lifecycle"]["status"] == "approved"
    assert payload["phase6_runtime_inputs"]["runtime_binding"] == "phase6_uses_canonical_twin_view"
