from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN = (ROOT / "services/decision-service/main.py").read_text()
PERSIST = (ROOT / "services/decision-service/persistence.py").read_text()
MIGRATION = (ROOT / "services/decision-service/migrations/008_learning_attribution.sql").read_text()
ROUTER = (ROOT / "services/sahool-platform/api/routers/decision_review.py").read_text()


def test_wx10_13_contract_is_attribution_only():
    assert "/v1/outcomes/{outcome_id}/learning-attribution" in MAIN
    assert "create_learning_attribution" in MAIN
    segment = MAIN[MAIN.index('@app.post("/v1/outcomes/{outcome_id}/learning-attribution")') :]
    assert "persist_learning_update(" not in segment
    assert "model.fit" not in segment
    assert "redispatch" not in segment.lower()


def test_attribution_persistence_is_traceable_and_append_only():
    for token in (
        "decision_learning_attributions",
        "outcome_id",
        "decision_id",
        "execution_request_id",
        "evidence_snapshot_id",
        "model_id",
        "learning_state",
        "LEARNING_ATTRIBUTION_CREATED",
    ):
        assert token in PERSIST
    assert "verified_success" in PERSIST and "verified_failure" in PERSIST
    assert "label_outcome_mismatch" in PERSIST
    assert "evidence_snapshot_mismatch" in PERSIST
    assert "append-only" in MIGRATION
    assert "BEFORE UPDATE OR DELETE" in MIGRATION


def test_bff_proves_authoritative_attribution():
    assert "/api/v1/outcomes/{outcome_id}/learning-attribution" in ROUTER
    assert "Permission.DECISION_LEARNING_ATTRIBUTE" in ROUTER
    assert 'result.get("authoritative") is True' in ROUTER
    assert 'result.get("persisted") is True' in ROUTER
    assert 'learning_state") == "attributed"' in ROUTER
