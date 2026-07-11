from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN = (ROOT / "services/decision-service/main.py").read_text()
PERSIST = (ROOT / "services/decision-service/persistence.py").read_text()
ROUTER = (ROOT / "services/sahool-platform/api/routers/decision_review.py").read_text()
MIG = (ROOT / "services/decision-service/migrations/010_model_promotion_decision.sql").read_text()


def test_wx11_3_contract_present():
    assert '@app.post("/v1/learning/promotion-decisions")' in MAIN
    assert "/api/v1/learning/promotion-decisions" in ROUTER
    assert "decision_model_promotion_decisions" in MIG
    assert "MODEL_PROMOTION_DECISION_CREATED" in PERSIST


def test_wx11_3_is_decision_only():
    segment = MAIN[MAIN.index("class ModelPromotionDecisionIn") :]
    for token in ("model.fit(", "optimizer.step(", "active_model", "mqtt.publish("):
        assert token not in segment


def test_wx11_3_policy_and_append_only():
    assert "promotion_eligible" in MIG and "promotion_rejected" in MIG
    assert "uq_model_promotion_evaluation" in MIG
    assert "append-only" in MIG
    assert "primary_metric_below_threshold" in PERSIST
    assert "guardrail_regression" in PERSIST
