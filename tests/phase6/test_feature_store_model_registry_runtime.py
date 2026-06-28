from shared.continuous_learning_phase10 import run_phase10_learning_cycle
from shared.feature_store import (
    build_point_in_time_snapshot,
    materialize_online_feature_values,
    register_feature_definitions,
    write_offline_feature_dataset,
)
from shared.mlops import apply_model_promotion, register_model_version, rollback_serving_alias


def _records():
    return [
        {
            "feature_id": f"feat_{i}",
            "entity_type": "field",
            "entity_id": "field-a" if i < 3 else "field-b",
            "event_time": f"2026-06-26T0{i}:00:00+00:00",
            "features": {"ndvi": 0.40 + i * 0.02, "etc_mm": 4.0 + i},
            "labels": {"net_benefit": 10 + i},
        }
        for i in range(6)
    ]


def test_feature_store_registers_versions_and_point_in_time_snapshot():
    records = _records()
    registry = register_feature_definitions(records, name="field-vigor", version="v1")
    assert registry["feature_set"]["feature_names"] == ["etc_mm", "ndvi"]
    assert all(d["feature_id"].startswith("featdef_") for d in registry["definitions"])

    offline = write_offline_feature_dataset(records, feature_set_id=registry["feature_set"]["feature_set_id"])
    assert offline["point_in_time_safe"] is True
    assert offline["row_count"] == 6
    assert len(offline["content_hash"]) == 64

    snapshot = build_point_in_time_snapshot(records, as_of="2026-06-26T04:30:00+00:00")
    assert snapshot["row_count"] == 2
    assert {r["entity_id"] for r in snapshot["rows"]} == {"field-a", "field-b"}

    online = materialize_online_feature_values(records, feature_set_id=registry["feature_set"]["feature_set_id"])
    assert online["write_count"] == 2
    assert all(w["online_key"].startswith(registry["feature_set"]["feature_set_id"]) for w in online["writes"])


def test_model_registry_promotion_and_rollback_are_fail_closed():
    champion = register_model_version(
        model_name="yield-risk",
        version="1.0.0",
        task="agronomic_recommendation",
        artifacts={"uri": "minio://models/yield-risk/1.0.0/model.pkl"},
        metrics={"score": 0.80},
        status="champion",
    )
    challenger = register_model_version(
        model_name="yield-risk",
        version="1.1.0",
        task="agronomic_recommendation",
        artifacts={"uri": "minio://models/yield-risk/1.1.0/model.pkl"},
        metrics={"score": 0.85},
        status="candidate",
    )
    promotion = apply_model_promotion(alias="agronomic:prod", champion=champion, challenger=challenger)
    assert promotion["decision"] == "promote"
    assert promotion["target_model_id"] == challenger["model_id"]
    rb = rollback_serving_alias(alias="agronomic:prod", current_model_id=challenger["model_id"], target_model_id=champion["model_id"], reason="smoke_failure")
    assert rb["to_model_id"] == champion["model_id"]


def test_phase10_cycle_emits_production_feature_store_and_model_registry_runtime():
    out = run_phase10_learning_cycle(
        phase9_cycle={"cycle_id": "auto-1", "feature_store_batch": _records(), "canonical_state": {"field_id": "field-a", "state": {}}},
        champion_model={"model_id": "champion", "name": "yield-risk", "version": "1.0.0", "task": "agronomic_recommendation", "metrics": {"score": 0.8}, "artifacts": {"uri": "minio://models/yield-risk/1.0.0"}},
        challenger_model={"model_id": "challenger", "name": "yield-risk", "version": "1.1.0", "task": "agronomic_recommendation", "status": "candidate", "metrics": {"score": 0.84}, "artifacts": {"uri": "minio://models/yield-risk/1.1.0"}},
    )
    fs = out["feature_store_runtime"]
    ml = out["model_registry_runtime"]
    assert fs["offline_dataset_version"]["point_in_time_safe"] is True
    assert fs["online_materialization"]["write_count"] == 2
    assert ml["champion"]["status"] == "champion"
    assert ml["serving_promotion"]["decision"] in {"promote", "blocked"}
    assert ml["rollback_plan"] is not None
