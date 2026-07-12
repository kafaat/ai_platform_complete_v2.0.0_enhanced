"""Terminal runtime lineage: rollback/rollout/dispatch receipts + rollback-aware monitoring."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_migration_covers_terminal_runtime_lineage():
    text = (
        ROOT / "services/decision-service/migrations/023_runtime_terminal_agronomic_lineage.sql"
    ).read_text()
    for token in (
        "decision_assert_rollback_command_cohorts",
        "decision_assert_rollback_receipt_cohorts",
        "decision_assert_rollout_receipt_cohorts",
        "decision_assert_retraining_dispatch_cohorts",
        "source_transition_type",
    ):
        assert token in text


def test_runtime_persistence_inherits_terminal_cohorts():
    text = (ROOT / "services/decision-service/persistence.py").read_text()
    assert 'plan["agronomic_cohorts"]' in text
    assert 'request["agronomic_cohorts"]' in text
    assert 'command["agronomic_cohorts"]' in text
    assert 'active["source_transition_type"]' in text
    assert "'rollback'::text source_transition_type" in text
