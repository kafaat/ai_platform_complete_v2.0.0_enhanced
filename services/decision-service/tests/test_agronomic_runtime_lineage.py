"""Runtime cohort lineage: monitoring bound to the active receipt; retraining to drift."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
M = (
    ROOT / "services/decision-service/migrations/022_runtime_agronomic_cohort_lineage.sql"
).read_text()
P = (ROOT / "services/decision-service/persistence.py").read_text()
MAIN = (ROOT / "services/decision-service/main.py").read_text()


def test_runtime_tables_carry_agronomic_cohorts():
    for table in (
        "decision_model_registry_activation_receipts",
        "decision_model_post_activation_verifications",
        "decision_model_rollout_plans",
        "decision_model_monitoring_snapshots",
        "decision_model_retraining_requests",
    ):
        assert table in M
    assert "agronomic_cohort_fingerprint" in M


def test_monitoring_is_bound_to_active_receipt():
    assert "active_model_receipt_required" in P
    assert "source_receipt_id" in P
    assert "decision_assert_monitoring_cohorts" in M


def test_retraining_is_bound_to_drift_and_monitoring():
    assert "retraining_requires_drift_signal" in P
    assert "source_monitoring_snapshot_id" in P
    assert "decision_assert_retraining_cohorts" in M
    assert 'target_environment: str = "production"' in MAIN
