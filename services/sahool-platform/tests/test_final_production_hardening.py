from core.canonical_field_state_lock import FieldAnnotation, FieldSignal, compose_locked_field_state
from core.data_quality_guard import validate_agronomic_ranges
from core.feature_store import FeatureValue, default_feature_registry
from core.field_digital_twin import FieldTwinState, simulate_irrigation, simulate_salinity_risk
from core.field_event_sourcing import FieldEvent, replay_field_events
from core.human_feedback_learning import RecommendationFeedback, feedback_summary, should_retrain
from core.mlops_registry import MLOpsRegistryError, ModelCard, ModelRegistry


def test_event_sourcing_replays_field_at_timestamp_without_cross_tenant_leak():
    events = [
        FieldEvent("T1", "F1", "FieldCreated", {"crop": "wheat"}, "2026-01-01T00:00:00Z"),
        FieldEvent("T2", "F1", "LabResultAdded", {"soil_ec_ds_m": 99}, "2026-01-02T00:00:00Z"),
        FieldEvent("T1", "F1", "LabResultAdded", {"soil_ec_ds_m": 3.2}, "2026-01-03T00:00:00Z"),
        FieldEvent("T1", "F1", "HarvestRecorded", {"yield_t_ha": 4.1}, "2026-07-01T00:00:00Z"),
    ]
    history = replay_field_events(events, tenant_id="T1", field_id="F1", at="2026-03-01T00:00:00Z")
    assert history.field["crop"] == "wheat"
    assert history.lab_results == [
        {
            "soil_ec_ds_m": 3.2,
            "event_id": events[2].stable_id,
            "occurred_at": "2026-01-03T00:00:00Z",
        }
    ]
    assert history.harvests == []


def test_event_sourcing_rejects_direct_decision_payloads():
    try:
        FieldEvent(
            "T1", "F1", "SatelliteUpdated", {"raw_decision": "spray"}, "2026-01-01T00:00:00Z"
        )
    except Exception as exc:
        assert "bypass" in str(exc)
    else:
        raise AssertionError("event accepted decision payload")


def test_feature_registry_requires_canonical_source_and_validates_values():
    registry = default_feature_registry()
    spec = registry.get("soil_ec_ds_m")
    value = FeatureValue("T1", "F1", spec, 2.5, "2026-01-01T00:00:00Z", "high")
    assert registry.validate_values([value])["valid"] is True


def test_data_quality_blocks_impossible_values_and_warns_on_salinity_indication():
    report = validate_agronomic_ranges({"soil_ph": 14, "salinity_index": 0.8, "ndvi": 0.4})
    assert report.blocks_decision is True
    assert any(i.field == "soil_ec_ds_m" and i.severity == "warning" for i in report.issues)


def test_digital_twin_simulates_without_emitting_recommendation():
    twin = FieldTwinState("F1", {"soil_moisture_pct": 15, "soil_ec_ds_m": 4.0})
    irrigated = simulate_irrigation(twin, 30)
    risked = simulate_salinity_risk(irrigated)
    assert risked.predicted["soil_moisture_pct_after_irrigation"] == 39.0
    assert risked.risks["water_stress"] == "low"
    assert risked.risks["salinity"] == "medium"
    assert "recommendation" not in risked.predicted


def test_mlops_registry_blocks_underpowered_champion_models():
    registry = ModelRegistry()
    try:
        registry.register(
            ModelCard("yield", "v1", "yield_prediction", "champion", 10, {"rmse": 1.0}, ("ndvi",))
        )
    except MLOpsRegistryError:
        pass
    else:
        raise AssertionError("underpowered champion model was accepted")
    registry.register(
        ModelCard(
            "yield", "v2", "yield_prediction", "champion", 80, {"rmse": 0.4}, ("ndvi", "et0_mm")
        )
    )
    assert registry.champion_for("yield_prediction").version == "v2"


def test_feedback_learning_uses_outcome_pairs_and_retraining_gate():
    items = [
        RecommendationFeedback("R1", "S1", "accepted"),
        RecommendationFeedback("R2", "S2", "modified"),
        RecommendationFeedback("R3", "S3", "outcome", predicted_value=3.0, actual_value=2.0),
    ]
    summary = feedback_summary(items)
    assert summary["total"] == 3
    assert summary["outcome_pairs"] == 1
    assert summary["rmse"] == 1.0
    assert should_retrain(items, min_outcomes=2) is False


def test_rag_and_kg_annotations_do_not_enter_recommendation_inputs():
    state = compose_locked_field_state(
        field_id="F1",
        tenant_id="T1",
        signals=[FieldSignal("soil_ec_ds_m", "lab", 3.5, True, "governing", "lab")],
        annotations=[
            FieldAnnotation(
                "nitrogen_note", "rag", "manual says yellowing may be nitrogen", "manual"
            )
        ],
        lifecycle="ready",
    )
    assert state.recommendation_inputs == {"soil_ec_ds_m": 3.5}
    assert state.explanatory_annotations[0]["verified"] is False
