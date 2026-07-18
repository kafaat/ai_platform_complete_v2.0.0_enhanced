from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "services/decision-service/main.py").read_text(encoding="utf-8")
PERSIST = (ROOT / "services/decision-service/persistence.py").read_text(encoding="utf-8")
SQL = (ROOT / "services/decision-service/migrations/014_wx11_closed_loop_completion.sql").read_text(
    encoding="utf-8"
)


def test_wx117_rollback_claim_receipt_contract():
    assert "decision_model_registry_rollback_claims" in SQL
    assert "decision_model_registry_rollback_receipts" in SQL
    assert "receipt_state IN ('rolled_back','rollback_failed')" in SQL
    assert "restored_artifact_digest_mismatch" in PERSIST


def test_wx118_active_state_is_receipt_derived():
    assert "/v1/learning/models/{model_id}/active-state" in MAIN
    assert "WITH activations AS" in PERSIST and "UNION ALL SELECT * FROM rollbacks" in PERSIST


def test_wx119_verification_requires_artifact_identity():
    assert "decision_model_post_activation_verifications" in SQL
    assert "artifact_digest_mismatch" in PERSIST
    assert "verified_healthy" in MAIN and "verification_failed" in MAIN


def test_wx1110_rollout_requires_verification():
    assert "decision_model_rollout_plans" in SQL
    assert "post_activation_verification_required" in PERSIST
    assert 'mode not in {"shadow", "canary", "full"}' in MAIN


def test_wx1111_monitoring_is_evidence_only():
    assert "decision_model_monitoring_snapshots" in SQL
    assert "drift_state IN ('stable','warning','critical')" in SQL
    assert "MODEL_MONITORING_SNAPSHOT_RECORDED" in PERSIST


def test_wx1112_retraining_is_request_only():
    assert "decision_model_retraining_requests" in SQL
    assert "request_state='queued'" in SQL
    assert "MODEL_RETRAINING_REQUEST_CREATED" in PERSIST
    assert "model.fit(" not in PERSIST and "optimizer.step(" not in PERSIST
