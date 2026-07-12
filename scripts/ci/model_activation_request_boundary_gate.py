from pathlib import Path

root = Path(__file__).resolve().parents[2]
main = (root / "services/decision-service/main.py").read_text()
persist = (root / "services/decision-service/persistence.py").read_text()
migration = (
    root / "services/decision-service/migrations/011_model_activation_request.sql"
).read_text()
router = (root / "services/sahool-platform/api/routers/decision_review.py").read_text()
assert "/v1/learning/activation-requests" in main
assert "/api/v1/learning/activation-requests" in router
assert "MODEL_ACTIVATION_REQUEST_CREATED" in persist
assert "pending_activation_approval" in migration
assert "promotion_eligible" in persist
assert "append-only" in migration
start = main.index("class ModelActivationRequestIn")
end = main.index("class ModelActivationReviewIn")
segment = main[start:end]
for forbidden in (
    "model.fit(",
    "partial_fit(",
    "optimizer.step(",
    "registry_alias",
    "active_model",
    "deploy_model",
    "mqtt.publish(",
    "actuator",
):
    assert forbidden not in segment, forbidden
print("WX-11.4 model activation request boundary: PASS")
