from pathlib import Path

root = Path(__file__).resolve().parents[2]
main = (root / "services/decision-service/main.py").read_text()
persist = (root / "services/decision-service/persistence.py").read_text()
migration = (
    root / "services/decision-service/migrations/012_model_activation_approval_command.sql"
).read_text()
router = (root / "services/sahool-platform/api/routers/decision_review.py").read_text()
auth = (root / "services/sahool-platform/core/authorization.py").read_text()
assert "/v1/learning/activation-requests/{activation_request_id}/review" in main
assert "/api/v1/learning/activation-requests/{activation_request_id}/review" in router
assert "MODEL_ACTIVATION_REQUEST_REVIEWED" in persist
assert "MODEL_REGISTRY_ACTIVATION_COMMAND_CREATED" in persist
assert "previous_artifact_digest" in migration and "command_state" in migration
assert "decision:model-activation-approve" in auth
assert "append-only" in migration
segment = main[main.index("class ModelActivationReviewIn") :]
for forbidden in (
    "model.fit(",
    "partial_fit(",
    "optimizer.step(",
    "set_alias(",
    "update_alias(",
    "deploy_model(",
    "mqtt.publish(",
    "actuator",
):
    assert forbidden not in segment, forbidden
print("WX-11.5 model activation approval boundary: PASS")
