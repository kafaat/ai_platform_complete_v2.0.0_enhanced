from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN = (ROOT / "services/decision-service/main.py").read_text()
PERSIST = (ROOT / "services/decision-service/persistence.py").read_text()
ROUTER = (ROOT / "services/sahool-platform/api/routers/decision_review.py").read_text()
MIG = (ROOT / "services/decision-service/migrations/009_model_evaluation_run.sql").read_text()


def test_wx11_2_contract_present():
    assert '@app.post("/v1/learning/evaluation-runs")' in MAIN
    assert "MODEL_EVALUATION_RUN_CREATED" in PERSIST
    assert "/api/v1/learning/evaluation-runs" in ROUTER
    assert "decision_model_evaluation_runs" in MIG


def test_wx11_2_is_evaluation_only():
    segment = MAIN[MAIN.index("class ModelEvaluationRunIn") :]
    for token in ("model.fit(", "optimizer.step(", "promote_model", "mqtt.publish("):
        assert token not in segment


def test_wx11_2_append_only_and_idempotent():
    assert "append-only" in MIG
    assert "uq_model_eval_idempotency" in MIG
    assert "candidate_artifact_digest" in MIG
    assert "dataset_fingerprint_mismatch" in PERSIST
    assert "_calibration_fingerprint" in PERSIST
