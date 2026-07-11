from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN = (ROOT / "services/decision-service/main.py").read_text()
PERSIST = (ROOT / "services/decision-service/persistence.py").read_text()
MIGRATION = (
    ROOT / "services/decision-service/migrations/012_model_activation_approval_command.sql"
).read_text()
ROUTER = (ROOT / "services/sahool-platform/api/routers/decision_review.py").read_text()
AUTH = (ROOT / "services/sahool-platform/core/authorization.py").read_text()


def test_activation_review_routes_and_permission():
    assert '@app.post("/v1/learning/activation-requests/{activation_request_id}/review")' in MAIN
    assert "/api/v1/learning/activation-requests/{activation_request_id}/review" in ROUTER
    assert "DECISION_MODEL_ACTIVATION_APPROVE" in AUTH


def test_approval_requires_rollback_pointer_and_queues_command():
    assert "previous_artifact_uri" in MAIN
    assert "previous_artifact_digest must be sha256 hex" in MAIN
    assert "command_state text NOT NULL DEFAULT 'queued'" in MIGRATION
    assert "MODEL_REGISTRY_ACTIVATION_COMMAND_CREATED" in PERSIST


def test_rejection_has_no_command_and_requires_reason():
    assert "review_reason is required for rejection" in MAIN
    assert 'if payload.review_decision == "approved"' in PERSIST


def test_records_are_append_only_and_no_direct_registry_mutation():
    assert MIGRATION.count("append-only") >= 2
    segment = MAIN[MAIN.index("class ModelActivationReviewIn") :]
    for forbidden in (
        "set_alias(",
        "update_alias(",
        "deploy_model(",
        "model.fit(",
        "optimizer.step(",
    ):
        assert forbidden not in segment
