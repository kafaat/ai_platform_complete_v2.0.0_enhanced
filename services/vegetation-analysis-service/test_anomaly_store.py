import pytest
from anomaly_store import AnomalyStore, InvalidTransition


def _payload():
    return {
        "anomaly_ref": "urn:sahool:anomaly:anomaly_demo",
        "tenant_id": "88ddb9f8-cf89-4398-a404-fe88ec4d4bb6",
        "field_id": "fld_demo",
        "season_id": "sea_demo",
        "signal_type": "ndvi_decline",
        "severity": "high",
    }


def test_lifecycle_and_optimistic_concurrency(tmp_path):
    store = AnomalyStore(str(tmp_path / "anomalies.db"))
    detected = store.upsert_detected(_payload())
    assert detected["status"] == "detected"
    requested = store.transition(
        detected["anomaly_ref"],
        "verification_requested",
        expected_version=1,
        task_ref="urn:sahool:task:task_1",
    )
    assert requested["aggregate_version"] == 2
    confirmed = store.transition(detected["anomaly_ref"], "confirmed", expected_version=2)
    assert confirmed["status"] == "confirmed"
    with pytest.raises(InvalidTransition):
        store.transition(detected["anomaly_ref"], "rejected", expected_version=2)


def test_invalid_state_transition_is_blocked(tmp_path):
    store = AnomalyStore(str(tmp_path / "anomalies.db"))
    detected = store.upsert_detected(_payload())
    with pytest.raises(InvalidTransition):
        store.transition(detected["anomaly_ref"], "confirmed", expected_version=1)
