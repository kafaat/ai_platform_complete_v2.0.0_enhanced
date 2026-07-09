from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROBE = ROOT / "services" / "decision-service" / "staging_probe.py"
GATE = ROOT / "scripts" / "ci" / "decision_sor_staging_probe_gate.py"
WORKFLOW = ROOT / ".github" / "workflows" / "field-workspace-production-closure.yml"
RUNBOOK = ROOT / "docs" / "runbooks" / "DECISION_SERVICE_SOR_STAGING_PROBE_RUNBOOK.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_staging_probe_is_safe_by_default(capsys) -> None:
    module = _load_module("decision_sor_staging_probe_p04", PROBE)
    rc = module.main([])
    assert rc == 0
    body = json.loads(capsys.readouterr().out)
    assert body["mode"] == "dry-run"
    assert body["ok"] is True
    assert "live network/db checks skipped" in body["steps"][0]["detail"]


def test_live_probe_refuses_production(monkeypatch) -> None:
    module = _load_module("decision_sor_staging_probe_p04_prod", PROBE)
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.setenv("DECISION_SERVICE_STAGING_PROBE_APPROVED", "true")
    monkeypatch.setenv("DECISION_SERVICE_STAGING_PROBE_ALLOW_LIVE", "true")
    try:
        module.main(["--live"])
    except SystemExit as exc:
        assert "production" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("live probe must refuse production")


def test_live_probe_requires_explicit_staging_approval(monkeypatch) -> None:
    module = _load_module("decision_sor_staging_probe_p04_approval", PROBE)
    monkeypatch.setenv("SAHOOL_ENV", "staging")
    monkeypatch.delenv("DECISION_SERVICE_STAGING_PROBE_APPROVED", raising=False)
    monkeypatch.setenv("DECISION_SERVICE_STAGING_PROBE_ALLOW_LIVE", "true")
    try:
        module.main(["--live"])
    except SystemExit as exc:
        assert "DECISION_SERVICE_STAGING_PROBE_APPROVED" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("live probe must require explicit staging approval")


def test_staging_probe_contains_required_cutover_checks() -> None:
    text = _read(PROBE)
    for token in (
        "migration_runner.py",
        "backfill.py",
        "--verify-counts",
        "/v1/cutover/readiness",
        "can_enable_sor",
        "can_demote_platform",
        "SAHOOL_DECISION_WRITE_MODE",
        "--sample-write",
        "idempotency-key",
    ):
        assert token in text


def test_p04_gate_and_ci_are_wired() -> None:
    gate = _read(GATE)
    workflow = _read(WORKFLOW)
    assert "Decision SoR staging probe gate passed" in gate
    assert "decision_sor_staging_probe_gate.py" in workflow
    assert "test_p0_4_decision_sor_staging_probe_guard.py" in workflow


def test_p04_runbook_documents_safe_operator_sequence() -> None:
    text = _read(RUNBOOK)
    for phrase in (
        "dry-run first",
        "DECISION_SERVICE_STAGING_PROBE_APPROVED=true",
        "DECISION_SERVICE_STAGING_PROBE_ALLOW_LIVE=true",
        "SAHOOL_ENV=staging",
        "do not run in production",
        "--sample-write",
    ):
        assert phrase in text


def test_new_p04_python_files_compile() -> None:
    for path in (PROBE, GATE):
        compile(_read(path), str(path), "exec")
