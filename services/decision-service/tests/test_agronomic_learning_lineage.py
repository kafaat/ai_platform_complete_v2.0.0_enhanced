"""AC-9 static contract: learning rows inherit the exact agronomic evidence of their decision."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (
    ROOT / "services/decision-service/migrations/020_learning_agronomic_lineage.sql"
).read_text()
PERSISTENCE = (ROOT / "services/decision-service/persistence.py").read_text()


def test_migration_propagates_governed_agronomic_lineage():
    for column in (
        "agronomic_context_snapshot_id",
        "vegetation_snapshot_id",
        "field_historical_context_snapshot_id",
        "feature_manifest_id",
        "feature_manifest_hash",
        "crop_id",
        "cultivar_id",
        "season_id",
    ):
        assert column in MIGRATION
    assert "enforce_learning_agronomic_lineage" in MIGRATION
    assert "must exactly match source decision" in MIGRATION
    # deviation from the delivered bundle (documented): RLS is ENABLEd with the tenant
    # policy but NOT forced — FORCE lands with the non-owner runtime role cutover.
    assert "ENABLE ROW LEVEL SECURITY" in MIGRATION


def test_learning_write_inherits_lineage_from_decision_not_request():
    assert "JOIN decision_record d" in PERSISTENCE
    assert 'source["agronomic_context_snapshot_id"]' in PERSISTENCE
    assert 'source["vegetation_snapshot_id"]' in PERSISTENCE
    assert 'source["field_historical_context_snapshot_id"]' in PERSISTENCE
    assert 'source["feature_manifest_hash"]' in PERSISTENCE


def test_calibration_fingerprint_and_items_include_agronomic_lineage():
    assert (
        '"agronomic_context_snapshot_id": item.get("agronomic_context_snapshot_id")' in PERSISTENCE
    )
    assert '"feature_manifest_hash": item.get("feature_manifest_hash")' in PERSISTENCE
    assert '"agronomic_cohorts": cohort_counts' in PERSISTENCE


def test_calibration_dataset_excludes_ungrounded_legacy_decisions():
    for token in (
        "d.agronomic_context_snapshot_id IS NOT NULL",
        "d.vegetation_snapshot_id IS NOT NULL",
        "d.field_historical_context_snapshot_id IS NOT NULL",
        "d.feature_manifest_hash IS NOT NULL",
        "d.cultivar_id IS NOT NULL",
    ):
        assert token in PERSISTENCE
