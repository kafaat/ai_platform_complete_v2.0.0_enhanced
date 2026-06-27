from shared.autonomous_farm_os_phase9 import (
    event_source_execution_plan,
    plan_closed_loop_execution,
    replay_autonomy_events,
    run_command_verification_loop,
)
from shared.continuous_learning_phase10 import (
    detect_feature_drift,
    infer_feature_schema,
    materialize_training_dataset,
    plan_retraining_job,
    run_champion_challenger_cycle,
    run_phase10_learning_cycle,
)


def _recommendation():
    return {
        "recommendation_id": "rec-1",
        "source_state_id": "state-1",
        "field_id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "22222222-2222-2222-2222-222222222222",
        "status": "approved",
        "action_type": "irrigation",
        "decision": {"operator_approved": True, "risk_score": 0.1, "water_mm": 12},
        "evidence": {},
    }


def test_phase9_event_source_replay_reconstructs_dispatch_ready_state():
    plan = plan_closed_loop_execution(
        _recommendation(),
        mode="supervised_autonomy",
        policy={"max_risk_score": 0.5},
        actuator_registry={
            "11111111-1111-1111-1111-111111111111": {"protocol": "mqtt", "target_id": "pivot-1"}
        },
    )
    events = event_source_execution_plan(plan)
    replayed = replay_autonomy_events(events)
    assert len(events) >= 3
    assert replayed["status"] == "dispatched"
    assert replayed["recommendation_id"] == "rec-1"
    assert replayed["commands"][0]["protocol"] == "mqtt"


def test_phase9_command_verification_loop_closes_with_sensor_evidence():
    plan = plan_closed_loop_execution(
        _recommendation(),
        mode="full_autonomy",
        policy={"max_risk_score": 0.5, "full_autonomy_enabled": True},
        actuator_registry={
            "11111111-1111-1111-1111-111111111111": {"protocol": "mqtt", "target_id": "pivot-1"}
        },
    )
    cmd = plan["commands"][0]["command_id"]
    result = run_command_verification_loop(
        plan,
        telemetry_frames=[{"acknowledged_command_ids": [cmd], "flow_rate": 18.5, "pressure": 2.2}],
        before_state={"state": {"operational_truths": {"ndvi": 0.42}}},
        after_state={
            "state": {"operational_truths": {"ndvi": 0.45, "effective_status": "improving"}}
        },
    )
    assert result["verification"]["closed_loop"] is True
    assert result["verification"]["ack_complete"] is True
    assert result["verification"]["sensor_ok"] is True
    assert result["replayed_state"]["status"] == "effect_verified"


def _records(shift=0.0, n=12):
    return [
        {
            "feature_id": f"feat-{i}",
            "entity_type": "field",
            "entity_id": f"field-{i % 3}",
            "features": {"ndvi": 0.4 + shift + i * 0.01, "soil_moisture": 0.2 + shift},
            "labels": {"operation_completed": 1},
        }
        for i in range(n)
    ]


def test_phase10_detects_drift_and_plans_retraining():
    records = _records(shift=0.8)
    spec = infer_feature_schema(records)
    dataset = materialize_training_dataset(records, feature_set_spec=spec)
    drift = detect_feature_drift(
        baseline_stats={
            "ndvi": {"mean": 0.4, "std": 0.1},
            "soil_moisture": {"mean": 0.2, "std": 0.1},
        },
        current_records=records,
    )
    job = plan_retraining_job(
        drift=drift, dataset=dataset, model={"model_id": "mdl-1", "version": "v1"}
    )
    assert drift["decision"] in {"retrain", "block_promotion"}
    assert job["action"] == "queue_retraining"
    assert job["reproducibility"]["feature_set_id"] == dataset["feature_set_id"]


def test_phase10_champion_challenger_blocks_promotion_under_material_drift():
    records = _records(shift=1.0)
    dataset = materialize_training_dataset(records, feature_set_spec=infer_feature_schema(records))
    drift = detect_feature_drift(
        baseline_stats={"ndvi": {"mean": 0.4, "std": 0.1}}, current_records=records
    )
    cycle = run_champion_challenger_cycle(
        task="irrigation",
        champion={"model_id": "champ", "metrics": {"score": 0.8}},
        challenger={"model_id": "chall", "metrics": {"score": 0.95}, "status": "candidate"},
        dataset=dataset,
        drift=drift,
    )
    assert cycle["promotion"]["decision"] == "blocked"
    assert "drift_blocks_promotion" in cycle["promotion"]["reasons"]


def test_phase10_learning_cycle_emits_drift_lineage_and_retraining_job():
    phase9_cycle = {
        "cycle_id": "auto-1",
        "feature_store_batch": _records(),
        "canonical_state": {"field_id": "f1", "state": {}},
    }
    result = run_phase10_learning_cycle(
        phase9_cycle=phase9_cycle,
        champion_model={
            "model_id": "champ",
            "task": "irrigation",
            "version": "v1",
            "metrics": {"score": 0.8},
            "training_stats": {"ndvi": {"mean": 0.4, "std": 1.0}},
        },
        challenger_model={
            "model_id": "chall",
            "task": "irrigation",
            "metrics": {"score": 0.83},
            "status": "candidate",
        },
    )
    assert "drift_report" in result
    assert "feature_lineage" in result
    assert "retraining_job" in result
    assert "champion_challenger" in result
