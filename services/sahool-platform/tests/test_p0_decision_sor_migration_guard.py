from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DECISION_SERVICE = ROOT / "services" / "decision-service"
MAIN = DECISION_SERVICE / "main.py"
PERSISTENCE = DECISION_SERVICE / "persistence.py"
MIGRATION = DECISION_SERVICE / "migrations" / "001_decision_sor.sql"
REQS = DECISION_SERVICE / "requirements.txt"
PLATFORM_ROUTER = ROOT / "services" / "sahool-platform" / "api" / "routers" / "decision_record.py"
WORKFLOW = ROOT / ".github" / "workflows" / "field-workspace-production-closure.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_decision_service_sor_is_feature_gated_not_default_cutover() -> None:
    main = _read(MAIN)
    persistence = _read(PERSISTENCE)
    assert "DECISION_SERVICE_SOR_ENABLED" in main
    assert "sor_enabled()" in main
    assert "sor_enabled()" in persistence
    assert "DATABASE_URL" in persistence
    # Default behavior must remain the safe mirror mode until real DB cutover is deliberately enabled.
    assert "if sor_enabled():" in main
    assert "return _mirror_ack" in main
    assert "sahool-platform (temporary)" in main


def test_decision_service_has_real_persistence_adapter_and_outbox() -> None:
    text = _read(PERSISTENCE)
    for symbol in (
        "persist_decision_record",
        "persist_dispatch_decision",
        "persist_outcome_record",
        "persist_recommendation_outcome",
        "persist_learning_update",
        "emit_outbox_event",
        "list_decision_records",
    ):
        assert f"async def {symbol}" in text
    assert "asyncpg.connect" in text
    assert "decision_outbox_events" in text
    assert "ON CONFLICT" in text
    assert "learning update must be traceable" in text


def test_decision_service_migration_owns_closed_loop_tables() -> None:
    sql = _read(MIGRATION)
    for table in (
        "decision_record",
        "dispatch_decisions",
        "outcome_record",
        "recommendation_outcomes",
        "online_learning_updates",
        "decision_outbox_events",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "ux_outcome_record_tenant_idempotency" in sql
    assert "ck_learning_traceable" in sql
    assert "idx_decision_outbox_pending" in sql
    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto" in sql


def test_decision_service_default_runtime_still_truthful_mirror(monkeypatch) -> None:
    monkeypatch.delenv("DECISION_SERVICE_SOR_ENABLED", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sys.path.insert(0, str(DECISION_SERVICE))
    try:
        spec = importlib.util.spec_from_file_location("decision_service_main_guard", MAIN)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        from fastapi.testclient import TestClient

        client = TestClient(module.app)
        res = client.post(
            "/v1/decisions/record",
            headers={"X-Tenant-Id": "00000000-0000-0000-0000-000000000001"},
            json={"decision_type": "irrigation", "decision_value": {"action": "irrigate"}},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["accepted"] is True
        assert body["authoritative"] is False
        assert body["persisted"] is False
        assert "mirror-only" in body["note"]
        contract = client.get("/contract").json()
        assert contract["authoritative"] is False
        assert contract["persistence_gate"] == "DECISION_SERVICE_SOR_ENABLED=true + DATABASE_URL"
    finally:
        try:
            sys.path.remove(str(DECISION_SERVICE))
        except ValueError:
            pass


def test_platform_not_demoted_until_sor_cutover_is_verified() -> None:
    text = _read(PLATFORM_ROUTER)
    assert "tenant_connection(user)" in text
    assert "INSERT INTO decision_record" in text
    assert "INSERT INTO outcome_record" in text
    assert "_mirror_to_decision_service" in text
    assert "best-effort" in text or "best effort" in text


def test_decision_service_requirements_and_ci_include_sor_guard() -> None:
    assert "asyncpg==" in _read(REQS)
    workflow = _read(WORKFLOW)
    assert "test_p0_decision_sor_migration_guard.py" in workflow
