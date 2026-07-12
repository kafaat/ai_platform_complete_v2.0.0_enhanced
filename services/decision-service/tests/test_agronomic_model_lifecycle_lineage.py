"""Model lifecycle cohort lineage: evaluation → promotion → activation carry the cohorts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PERSISTENCE = (ROOT / "services/decision-service/persistence.py").read_text()
MIGRATION = (
    ROOT / "services/decision-service/migrations/021_model_agronomic_cohort_lineage.sql"
).read_text()


def test_evaluation_rebuilds_grounded_calibration_fingerprint():
    assert "d.agronomic_context_snapshot_id" in PERSISTENCE
    assert '"feature_manifest_hash": r["feature_manifest_hash"]' in PERSISTENCE
    assert "_agronomic_cohort_manifest(fingerprint_items)" in PERSISTENCE


def test_cohort_lineage_propagates_to_model_lifecycle():
    assert "agronomic_cohort_fingerprint" in PERSISTENCE
    assert 'evaluation["agronomic_cohorts"]' in PERSISTENCE
    assert 'promotion["agronomic_cohorts"]' in PERSISTENCE


def test_database_guards_cohort_substitution():
    assert "enforce_model_promotion_cohort_lineage" in MIGRATION
    assert "enforce_model_activation_cohort_lineage" in MIGRATION
    assert "must match evaluation" in MIGRATION
    assert "must match promotion" in MIGRATION
