from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DECISION = ROOT / "services" / "decision-service"
MIGRATION_RUNNER = DECISION / "migration_runner.py"
BACKFILL = DECISION / "backfill.py"
MAIN = DECISION / "main.py"
PERSISTENCE = DECISION / "persistence.py"
WORKFLOW = ROOT / ".github" / "workflows" / "field-workspace-production-closure.yml"
GATE = ROOT / "scripts" / "ci" / "decision_sor_cutover_readiness_gate.py"
RUNBOOK = ROOT / "docs" / "runbooks" / "DECISION_SERVICE_SOR_CUTOVER_RUNBOOK.md"
CONTRACT = ROOT / "docs" / "architecture" / "DECISION_SERVICE_SOR_CUTOVER_READINESS.md"
PLATFORM_ROUTER = ROOT / "services" / "sahool-platform" / "api" / "routers" / "decision_record.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_cutover_readiness_artifacts_exist() -> None:
    for path in (MIGRATION_RUNNER, BACKFILL, GATE, RUNBOOK, CONTRACT):
        assert path.exists(), path


def test_migration_runner_is_explicit_idempotent_and_drift_aware() -> None:
    text = _read(MIGRATION_RUNNER)
    assert "DECISION_SERVICE_ALLOW_SCHEMA_CHANGE" in text
    assert "Refusing to apply schema changes" in text
    assert "decision_service_schema_migrations" in text
    assert "checksum" in text
    assert "pg_advisory_xact_lock" in text
    assert "--check" in text and "--apply" in text
    assert "DATABASE_URL is required" in text
    assert "CREATE TABLE IF NOT EXISTS" in text


def test_backfill_verifier_supports_same_db_and_split_db_topologies() -> None:
    text = _read(BACKFILL)
    assert "--verify-counts" in text
    assert "PLATFORM_DATABASE_URL" in text
    assert "DECISION_DATABASE_URL" in text
    assert "same-db-verify" in text
    assert "cross-db-verify" in text
    for table in (
        "decision_record",
        "dispatch_decisions",
        "outcome_record",
        "recommendation_outcomes",
        "online_learning_updates",
    ):
        assert table in text


def test_cutover_runbook_requires_migration_backfill_staging_and_rollback() -> None:
    text = _read(RUNBOOK)
    for phrase in (
        "DECISION_SERVICE_SOR_ENABLED=true",
        "DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true",
        "migration_runner.py --check",
        "migration_runner.py --apply",
        "backfill.py --verify-counts",
        "rollback",
        "do not demote sahool-platform",
        "Tenant isolation",
    ):
        assert phrase in text


def test_sor_contract_preserves_strangler_invariants() -> None:
    text = _read(CONTRACT)
    for phrase in (
        "persisted=true",
        "DECISION_SERVICE_SOR_ENABLED=true",
        "sahool-platform remains the temporary authoritative writer",
        "Outbox rows are emitted",
        "Outcome writes must be idempotent",
        "Learning updates require lineage",
    ):
        assert phrase in text


def test_runtime_still_fails_closed_when_sor_requested_without_db(monkeypatch) -> None:
    monkeypatch.setenv("DECISION_SERVICE_SOR_ENABLED", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sys.path.insert(0, str(DECISION))
    try:
        spec = importlib.util.spec_from_file_location("decision_service_main_cutover_guard", MAIN)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        from fastapi.testclient import TestClient

        client = TestClient(module.app)
        ready = client.get("/readyz").json()
        assert ready["ready"] is False
        assert ready["sor_enabled"] is False
        assert ready["mode"] == "interim-mirror"
        res = client.post(
            "/v1/decisions/record",
            headers={"X-Tenant-Id": "00000000-0000-0000-0000-000000000001"},
            json={"decision_type": "irrigation", "decision_value": {"action": "irrigate"}},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["persisted"] is False
        assert body["authoritative"] is False
    finally:
        try:
            sys.path.remove(str(DECISION))
        except ValueError:
            pass


def test_platform_is_not_demoted_before_real_postgres_cutover() -> None:
    text = _read(PLATFORM_ROUTER)
    assert "tenant_connection(user)" in text
    assert "INSERT INTO decision_record" in text
    assert "INSERT INTO outcome_record" in text
    assert "_mirror_to_decision_service" in text


def test_static_cutover_gate_and_ci_are_wired() -> None:
    assert GATE.exists()
    gate = _read(GATE)
    assert "Decision SoR cutover readiness gate passed" in gate
    assert "migration_runner.py" in gate
    assert "backfill.py" in gate
    workflow = _read(WORKFLOW)
    assert "decision_sor_cutover_readiness_gate.py" in workflow
    assert "test_p0_2_decision_sor_cutover_readiness_guard.py" in workflow


def test_new_decision_service_python_files_compile() -> None:
    for path in (MIGRATION_RUNNER, BACKFILL, GATE, MAIN, PERSISTENCE):
        source = _read(path)
        compile(source, str(path), "exec")
