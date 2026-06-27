from core.production_readiness_gate import run_decision_readiness_gate


def test_readiness_gate_passes_when_decision_safety_modules_present():
    report = run_decision_readiness_gate(
        [
            "canonical_field_state_lock",
            "field_event_sourcing",
            "field_state_replay_bridge",
            "data_quality",
            "human_feedback_learning",
            "feature_store_contract",
        ]
    )
    assert report.passed is True
    assert report.failed == []


def test_readiness_gate_fails_closed_when_replay_bridge_missing():
    report = run_decision_readiness_gate(
        [
            "canonical_field_state_lock",
            "field_event_sourcing",
            "data_quality",
            "human_feedback_learning",
            "feature_store_contract",
        ]
    )
    assert report.passed is False
    assert any(check.name == "field_state_replay_bridge" for check in report.failed)
