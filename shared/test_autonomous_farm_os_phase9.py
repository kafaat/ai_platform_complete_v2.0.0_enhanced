from shared.autonomous_farm_os_phase9 import (
    AutonomyMode,
    assign_experiment_variant,
    build_feature_store_batch,
    evaluate_autonomy_safety_gate,
    plan_closed_loop_execution,
    register_model_version,
    run_phase9_autonomy_cycle,
    verify_execution_effect,
)


def _runtime():
    return {
        "runtime_id": "frt_1",
        "canonical_state": {"state_id": "cfs_1", "field_id": "field-1", "state": {"confidence": 0.82, "operational_truths": {"ndvi": 0.42}}},
        "digital_twin_view": {"field_id": "field-1", "limitations": []},
        "phase6_runtime_inputs": {"features": {"crop_vigor": "low", "etc_mm": 5.2, "kc": 0.9}},
        "recommendation_lifecycle": {
            "recommendation_id": "rec_1",
            "source_state_id": "cfs_1",
            "field_id": "field-1",
            "tenant_id": "tenant-1",
            "status": "approved",
            "action_type": "irrigation",
            "decision": {"action_type": "irrigation", "water_mm": 10, "operator_approved": True, "risk_score": 0.1},
            "evidence": {},
        },
    }


def test_safety_gate_is_fail_closed_for_unapproved_or_shadow():
    rec = _runtime()["recommendation_lifecycle"] | {"status": "proposed"}
    gate = evaluate_autonomy_safety_gate(rec, mode=AutonomyMode.SHADOW)
    assert gate["permitted"] is False
    assert "recommendation_not_approved" in gate["reasons"]
    assert "shadow_mode_no_dispatch" in gate["reasons"]


def test_closed_loop_execution_builds_idempotent_commands():
    rec = _runtime()["recommendation_lifecycle"]
    plan = plan_closed_loop_execution(
        rec,
        mode="full_autonomy",
        policy={"full_autonomy_enabled": True, "max_risk_score": 0.5},
        actuator_registry={"field-1": {"protocol": "mqtt", "target_id": "pivot-7"}},
    )
    assert plan["status"] == "dispatch_ready"
    assert plan["commands"][0]["protocol"] == "mqtt"
    assert plan["commands"][0]["idempotency_key"].startswith("idem_")


def test_verification_effect_and_feature_store_batch():
    rt = _runtime()
    plan = plan_closed_loop_execution(rt["recommendation_lifecycle"], mode="full_autonomy", policy={"full_autonomy_enabled": True})
    cmd_id = plan["commands"][0]["command_id"]
    verification = verify_execution_effect(plan, telemetry={"acknowledged_command_ids": [cmd_id], "applied": {"water_mm": 10}})
    assert verification["status"] == "effect_verified"
    batch = build_feature_store_batch(canonical_runtime=rt, execution_verification=verification)
    assert batch[0]["feature_set"] == "canonical_field_runtime_v1"
    assert batch[0]["labels"]["operation_completed"] is True


def test_model_registry_and_experiment_assignment_are_deterministic():
    model = register_model_version(name="yield", task="yield_prediction", version="1.0.0", metrics={"r2": 0.81}, training_feature_sets=["canonical_field_runtime_v1"], promote_thresholds={"r2": 0.8})
    assert model["status"] == "champion"
    a = assign_experiment_variant(entity_id="field-1", experiment_key="water_model", variants=["champion", "challenger"])
    b = assign_experiment_variant(entity_id="field-1", experiment_key="water_model", variants=["champion", "challenger"])
    assert a["variant"] == b["variant"]


def test_run_phase9_autonomy_cycle_produces_learning_candidate():
    cycle = run_phase9_autonomy_cycle(canonical_runtime=_runtime(), mode="full_autonomy", policy={"full_autonomy_enabled": True})
    assert cycle["phase"] == "phase9_autonomous_farm_os"
    assert cycle["verification"]["status"] == "effect_verified"
    assert cycle["learning_ready"] is True
