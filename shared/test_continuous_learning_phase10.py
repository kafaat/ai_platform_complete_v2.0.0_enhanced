from shared.continuous_learning_phase10 import (
    create_online_learning_update,
    decide_model_promotion,
    evaluate_experiment_outcomes,
    infer_feature_schema,
    materialize_training_dataset,
    run_phase10_learning_cycle,
    run_scientific_scenario,
)


def _records(n=12):
    return [
        {
            "feature_id": f"feat_{i}",
            "entity_type": "field",
            "entity_id": f"field-{i % 3}",
            "features": {"ndvi": 0.45 + i * 0.01, "etc_mm": 5 + i, "limitation_count": i % 2},
            "labels": {"operation_completed": i % 2 == 0, "net_benefit": 20 + i},
        }
        for i in range(n)
    ]


def test_feature_schema_and_dataset_trainable():
    records = _records()
    spec = infer_feature_schema(records)
    assert "ndvi" in spec["feature_names"]
    assert "net_benefit" in spec["label_names"]
    ds = materialize_training_dataset(records, feature_set_spec=spec)
    assert ds["status"] == "trainable"
    assert ds["row_count"] == 12
    assert ds["quality"]["label_coverage"] == 1.0


def test_dataset_blocks_low_rows():
    records = _records(2)
    spec = infer_feature_schema(records)
    ds = materialize_training_dataset(records, feature_set_spec=spec)
    assert ds["status"] == "blocked"
    assert "insufficient_rows" in ds["quality"]["blocked_reasons"]


def test_model_promotion_prefers_better_challenger():
    champion = {"model_id": "m1", "metrics": {"score": 0.70}}
    challenger = {"model_id": "m2", "status": "candidate", "metrics": {"score": 0.75}}
    decision = decide_model_promotion(task="yield", champion=champion, challenger=challenger, metric_policy={"primary_metric": "score", "min_improvement": 0.02})
    assert decision["decision"] == "promote_challenger"
    assert decision["metric_deltas"]["score"] > 0


def test_online_learning_detects_drift():
    records = _records()
    spec = infer_feature_schema(records)
    ds = materialize_training_dataset(records, feature_set_spec=spec)
    model = {"model_id": "m1", "training_stats": {"feature_mean": 0.1}, "online_learning_rate": 0.05}
    update = create_online_learning_update(model=model, dataset=ds, records=records, drift_threshold=0.1)
    assert update["action"] == "queue_retraining"
    assert update["sample_count"] == 12


def test_experiment_evaluation_selects_winner():
    assignments = [
        {"entity_id": "a", "experiment_key": "irrigation-v1", "variant": "control"},
        {"entity_id": "b", "experiment_key": "irrigation-v1", "variant": "control"},
        {"entity_id": "c", "experiment_key": "irrigation-v1", "variant": "challenger"},
        {"entity_id": "d", "experiment_key": "irrigation-v1", "variant": "challenger"},
    ]
    outcomes = [
        {"entity_id": "a", "net_benefit": 10},
        {"entity_id": "b", "net_benefit": 12},
        {"entity_id": "c", "net_benefit": 20},
        {"entity_id": "d", "net_benefit": 22},
    ]
    result = evaluate_experiment_outcomes(experiment_key="irrigation-v1", assignments=assignments, outcomes=outcomes)
    assert result["winner"] == "challenger"
    assert result["decision"] == "promote_variant"


def test_scientific_scenario_flags_yield_risk():
    field_state = {"field_id": "f1", "state": {"state_id": "s1", "crop": "wheat", "operational_truths": {"yield_t_ha": 4.0}}}
    result = run_scientific_scenario(field_state=field_state, scenario={"rainfall_delta_pct": -40, "sowing_delay_days": 20, "baseline_yield_t_ha": 4.0})
    assert result["projected"]["yield_t_ha"] < result["baseline"]["yield_t_ha"]
    assert "yield_decline_risk" in result["risk_flags"]


def test_phase10_cycle_builds_dataset_and_scenario():
    phase9 = {
        "cycle_id": "auto_1",
        "feature_store_batch": _records(),
        "canonical_state": {"field_id": "f1", "state": {"state_id": "s1", "operational_truths": {"yield_t_ha": 4}}},
    }
    out = run_phase10_learning_cycle(
        phase9_cycle=phase9,
        champion_model={"model_id": "m1", "task": "agronomic", "metrics": {"score": 0.7}},
        challenger_model={"model_id": "m2", "task": "agronomic", "status": "candidate", "metrics": {"score": 0.74}},
        scenario={"rainfall_delta_pct": -10, "baseline_yield_t_ha": 4},
    )
    assert out["phase"] == "phase10_continuous_learning_ai"
    assert out["training_dataset"]["status"] == "trainable"
    assert out["online_learning_update"] is not None
    assert out["scenario_result"] is not None
