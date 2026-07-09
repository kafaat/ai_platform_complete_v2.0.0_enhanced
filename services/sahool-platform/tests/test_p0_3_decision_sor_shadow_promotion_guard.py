from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DECISION = ROOT / "services" / "decision-service"
CUTOVER = DECISION / "cutover.py"
MAIN = DECISION / "main.py"
PLATFORM_MODE = ROOT / "services" / "sahool-platform" / "api" / "decision_sor_mode.py"
GATE = ROOT / "scripts" / "ci" / "decision_sor_shadow_promotion_gate.py"
WORKFLOW = ROOT / ".github" / "workflows" / "field-workspace-production-closure.yml"
PLATFORM_ROUTER = ROOT / "services" / "sahool-platform" / "api" / "routers" / "decision_record.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_decision_service_exposes_fail_closed_cutover_readiness_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("DECISION_SERVICE_SOR_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/unused")
    monkeypatch.delenv("DECISION_SERVICE_BACKFILL_VERIFIED", raising=False)
    sys.path.insert(0, str(DECISION))
    try:
        module = _load_module("decision_service_main_p03_guard", MAIN)
        from fastapi.testclient import TestClient

        client = TestClient(module.app)
        res = client.get("/v1/cutover/readiness")
        assert res.status_code == 200
        body = res.json()
        assert body["requested_sor"] is True
        assert body["can_enable_sor"] is False
        assert body["can_demote_platform"] is False
        assert "DECISION_SERVICE_BACKFILL_VERIFIED" in body["missing_gates"]
        assert "decision_record" in body["required_tables"]
    finally:
        try:
            sys.path.remove(str(DECISION))
        except ValueError:
            pass


def test_cutover_readiness_requires_backfill_tenant_outbox_and_approval() -> None:
    text = _read(CUTOVER)
    for token in (
        "DECISION_SERVICE_MIGRATIONS_VERIFIED",
        "DECISION_SERVICE_BACKFILL_VERIFIED",
        "DECISION_SERVICE_TENANT_ISOLATION_VERIFIED",
        "DECISION_SERVICE_OUTBOX_VERIFIED",
        "DECISION_SERVICE_STAGING_CUTOVER_APPROVED",
        "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED",
        "can_enable_sor",
        "can_demote_platform",
    ):
        assert token in text


def test_platform_write_mode_defaults_to_platform_sor_and_refuses_premature_demote(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAHOOL_DECISION_WRITE_MODE", "decision_service_sor")
    for name in (
        "DECISION_SERVICE_SOR_ENABLED",
        "DECISION_SERVICE_MIGRATIONS_VERIFIED",
        "DECISION_SERVICE_BACKFILL_VERIFIED",
        "DECISION_SERVICE_TENANT_ISOLATION_VERIFIED",
        "DECISION_SERVICE_OUTBOX_VERIFIED",
        "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED",
    ):
        monkeypatch.delenv(name, raising=False)
    module = _load_module("platform_decision_sor_mode_p03_guard", PLATFORM_MODE)
    mode = module.get_platform_decision_sor_mode()
    assert mode.effective_mode == "platform_sor"
    assert mode.platform_writes_required is True
    assert mode.mirror_required is True
    assert mode.demotion_allowed is False
    assert "DECISION_SERVICE_BACKFILL_VERIFIED" in mode.missing_gates


def test_platform_shadow_mode_keeps_platform_write_and_mirror(monkeypatch) -> None:
    monkeypatch.setenv("SAHOOL_DECISION_WRITE_MODE", "shadow")
    module = _load_module("platform_decision_sor_mode_p03_shadow", PLATFORM_MODE)
    mode = module.get_platform_decision_sor_mode()
    assert mode.effective_mode == "shadow"
    assert mode.platform_writes_required is True
    assert mode.mirror_required is True
    assert mode.strict_decision_service_required is False


def test_platform_demote_requires_explicit_production_cutover(monkeypatch) -> None:
    monkeypatch.setenv("SAHOOL_DECISION_WRITE_MODE", "decision_service_sor")
    for name in (
        "DECISION_SERVICE_SOR_ENABLED",
        "DECISION_SERVICE_MIGRATIONS_VERIFIED",
        "DECISION_SERVICE_BACKFILL_VERIFIED",
        "DECISION_SERVICE_TENANT_ISOLATION_VERIFIED",
        "DECISION_SERVICE_OUTBOX_VERIFIED",
        "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED",
    ):
        monkeypatch.setenv(name, "true")
    module = _load_module("platform_decision_sor_mode_p03_promote", PLATFORM_MODE)
    mode = module.get_platform_decision_sor_mode()
    assert mode.effective_mode == "decision_service_sor"
    assert mode.platform_writes_required is False
    assert mode.strict_decision_service_required is True
    assert mode.demotion_allowed is True


def test_platform_router_still_contains_authoritative_writes_until_runtime_cutover() -> None:
    text = _read(PLATFORM_ROUTER)
    assert "INSERT INTO decision_record" in text
    assert "INSERT INTO outcome_record" in text
    assert "_mirror_to_decision_service" in text


def test_shadow_promotion_gate_and_ci_are_wired() -> None:
    gate = _read(GATE)
    workflow = _read(WORKFLOW)
    assert "Decision SoR shadow promotion gate passed" in gate
    assert "decision_sor_shadow_promotion_gate.py" in workflow
    assert "test_p0_3_decision_sor_shadow_promotion_guard.py" in workflow


def test_new_p03_python_files_compile() -> None:
    for path in (CUTOVER, PLATFORM_MODE, GATE, MAIN):
        compile(_read(path), str(path), "exec")
