from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN = (ROOT / "services/decision-service/main.py").read_text()
PERSIST = (ROOT / "services/decision-service/persistence.py").read_text()
MIGRATION = (
    ROOT / "services/decision-service/migrations/011_model_activation_request.sql"
).read_text()
ROUTER = (ROOT / "services/sahool-platform/api/routers/decision_review.py").read_text()


def test_activation_request_contract_present():
    assert '@app.post("/v1/learning/activation-requests")' in MAIN
    assert "/api/v1/learning/activation-requests" in ROUTER
    assert "pending_activation_approval" in MIGRATION


def test_only_eligible_promotions_can_request_activation():
    assert "promotion_decision_not_eligible" in PERSIST
    assert "promotion_eligible" in PERSIST


def test_activation_request_is_not_activation():
    start = MAIN.index("class ModelActivationRequestIn")
    end = MAIN.index("class ModelActivationReviewIn")
    segment = MAIN[start:end]
    for forbidden in ("registry_alias", "active_model", "deploy_model", "model.fit("):
        assert forbidden not in segment


def test_append_only_and_outbox():
    assert "append-only" in MIGRATION
    assert "MODEL_ACTIVATION_REQUEST_CREATED" in PERSIST
