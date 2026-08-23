from pathlib import Path

root = Path(__file__).resolve().parents[2]
main = (root / "services/decision-service/main.py").read_text(encoding="utf-8")
persist = (root / "services/decision-service/persistence.py").read_text(encoding="utf-8")
migration = (
    root / "services/decision-service/migrations/010_model_promotion_decision.sql"
).read_text(encoding="utf-8")
router = (root / "services/sahool-platform/api/routers/decision_review.py").read_text(
    encoding="utf-8"
)
assert "/v1/learning/promotion-decisions" in main
assert "/api/v1/learning/promotion-decisions" in router
assert "MODEL_PROMOTION_DECISION_CREATED" in persist
assert "promotion_eligible" in migration and "promotion_rejected" in migration
assert "append-only" in migration
# Bound to the promotion-decision block only (class + handler), up to the next input model.
# Slicing to EOF would false-trip on WX-11.5/11.6 activation code that legitimately carries
# `registry_alias` — the contract is that the PROMOTION DECISION itself never activates/executes.
start = main.index("class ModelPromotionDecisionIn")
end = main.index("class ModelActivationRequestIn")
segment = main[start:end]
for forbidden in (
    "model.fit(",
    "partial_fit(",
    "optimizer.step(",
    "active_model",
    "registry_alias",
    "mqtt.publish(",
    "actuator",
):
    assert forbidden not in segment, forbidden
print("WX-11.3 model promotion decision boundary: PASS")
