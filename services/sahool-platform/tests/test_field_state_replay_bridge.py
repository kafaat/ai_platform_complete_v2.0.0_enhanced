from core.field_event_sourcing import FieldEvent
from core.field_state_replay_bridge import build_canonical_state_from_events


def test_replay_builds_canonical_state_without_decision_bypass():
    events = [
        FieldEvent(
            tenant_id="t1",
            field_id="f1",
            name="FieldCreated",
            payload={"crop": "wheat"},
            occurred_at="2026-01-01T00:00:00Z",
        ),
        FieldEvent(
            tenant_id="t1",
            field_id="f1",
            name="SatelliteUpdated",
            payload={"ndvi": 0.58, "quality": "clear", "capture_date": "2026-01-02"},
            occurred_at="2026-01-02T00:00:00Z",
        ),
        FieldEvent(
            tenant_id="t1",
            field_id="f1",
            name="LabResultAdded",
            payload={"ph": 7.4, "ec": 2.1, "source": "soil_lab"},
            occurred_at="2026-01-03T00:00:00Z",
        ),
        FieldEvent(
            tenant_id="t1",
            field_id="f1",
            name="RecommendationIssued",
            payload={"recommendation_id": "r1", "status": "draft"},
            occurred_at="2026-01-04T00:00:00Z",
        ),
    ]

    result = build_canonical_state_from_events(events, tenant_id="t1", field_id="f1")

    assert result.state.lifecycle == "ready"
    assert result.lab_count == 1
    assert result.satellite_count == 1
    assert result.recommendation_event_count == 1
    assert "lab_state" in result.state.recommendation_inputs
    assert "recommendation_history" not in result.state.recommendation_inputs
    assert result.state.explanatory_annotations[0]["name"] == "recommendation_history"


def test_replay_cutoff_rebuilds_prior_state():
    events = [
        FieldEvent("t1", "f1", "FieldCreated", {"crop": "wheat"}, "2026-01-01T00:00:00Z"),
        FieldEvent("t1", "f1", "LabResultAdded", {"ec": 2.1}, "2026-01-03T00:00:00Z"),
    ]

    result = build_canonical_state_from_events(
        events, tenant_id="t1", field_id="f1", at="2026-01-02T00:00:00Z"
    )

    assert result.state.lifecycle == "limited"
    assert result.state.recommendation_inputs == {}
