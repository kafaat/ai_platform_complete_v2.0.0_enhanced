"""Static guard for the first Decision tenant-boundary hardening slice."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "migrations/033_tenant_boundary_hardening.sql").read_text(encoding="utf-8")


def test_outbox_and_review_enable_and_force_rls():
    for table in ("decision_outbox_events", "decision_reviews"):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in SQL
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in SQL
        assert f"ON {table}" in SQL


def test_policy_is_fail_closed_without_tenant_context():
    assert "current_setting('app.current_tenant', true)" in SQL
    assert "NULLIF(" in SQL
    assert "USING (" in SQL
    assert "WITH CHECK (" in SQL


def test_scope_does_not_bulk_harden_unaudited_worker_tables():
    for table in (
        "decision_execution_requests",
        "decision_runtime_worker_tenants",
        "decision_model_runtime_work_claims",
    ):
        assert f"ALTER TABLE {table}" not in SQL
