from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/staging/s5_live_authority_closure.py"
spec = importlib.util.spec_from_file_location("s5_live_authority_closure", PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

SHA = "a" * 40


def _receipt(path: Path, schema: str, *, sha: str = SHA, promotion: bool = False) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": schema,
                "subject_sha": sha,
                "authority_promotion": promotion,
                "observed_at": "2026-08-18T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


def _paths(tmp_path: Path):
    d = tmp_path / "decision.json"
    f = tmp_path / "field.json"
    k = tmp_path / "kg.json"
    _receipt(d, mod.RECEIPTS["decision"]["receipt_schema"])
    _receipt(f, mod.RECEIPTS["field_management"]["receipt_schema"])
    _receipt(k, mod.RECEIPTS["knowledge_graph"]["receipt_schema"])
    return d, f, k


def test_three_canonical_guards_are_required_before_adjudication(tmp_path, monkeypatch):
    d, f, k = _paths(tmp_path)
    monkeypatch.setattr(
        mod, "_guard", lambda *a, **kw: {"passed": True, "returncode": 0, "output": "ok"}
    )
    body = mod.verify_receipts(subject_sha=SHA, decision_receipt=d, field_receipt=f, kg_receipt=k)
    assert body["classification"] == "PASSED"
    assert body["live_evidence_complete"] is True
    assert body["ready_for_authority_adjudication"] is True
    assert body["authority_promotion"] is False
    assert body["physical_shrink_authorized"] is False


def test_one_failed_domain_guard_blocks_the_whole_bundle(tmp_path, monkeypatch):
    d, f, k = _paths(tmp_path)

    def fake_guard(path, **kwargs):
        ok = path != f
        return {"passed": ok, "returncode": 0 if ok else 1, "output": "ok" if ok else "bad"}

    monkeypatch.setattr(mod, "_guard", fake_guard)
    body = mod.verify_receipts(subject_sha=SHA, decision_receipt=d, field_receipt=f, kg_receipt=k)
    assert body["classification"] == "FAILED"
    assert body["ready_for_authority_adjudication"] is False
    assert "field_management:canonical_guard_failed" in body["findings"]


def test_cross_subject_receipt_is_rejected_even_if_guard_is_stubbed_green(tmp_path, monkeypatch):
    d, f, k = _paths(tmp_path)
    _receipt(k, mod.RECEIPTS["knowledge_graph"]["receipt_schema"], sha="b" * 40)
    monkeypatch.setattr(
        mod, "_guard", lambda *a, **kw: {"passed": True, "returncode": 0, "output": "ok"}
    )
    body = mod.verify_receipts(subject_sha=SHA, decision_receipt=d, field_receipt=f, kg_receipt=k)
    assert body["classification"] == "FAILED"
    assert "knowledge_graph:subject_sha_mismatch" in body["findings"]


def test_receipt_that_claims_authority_promotion_is_rejected(tmp_path, monkeypatch):
    d, f, k = _paths(tmp_path)
    _receipt(d, mod.RECEIPTS["decision"]["receipt_schema"], promotion=True)
    monkeypatch.setattr(
        mod, "_guard", lambda *a, **kw: {"passed": True, "returncode": 0, "output": "ok"}
    )
    body = mod.verify_receipts(subject_sha=SHA, decision_receipt=d, field_receipt=f, kg_receipt=k)
    assert body["classification"] == "FAILED"
    assert "decision:receipt_must_not_promote_authority" in body["findings"]


def test_missing_receipt_fails_closed_without_crash(tmp_path, monkeypatch):
    d, f, k = _paths(tmp_path)
    k.unlink()
    monkeypatch.setattr(
        mod, "_guard", lambda *a, **kw: {"passed": True, "returncode": 0, "output": "ok"}
    )
    body = mod.verify_receipts(subject_sha=SHA, decision_receipt=d, field_receipt=f, kg_receipt=k)
    assert body["classification"] == "FAILED"
    assert "knowledge_graph:receipt_missing" in body["findings"]


def test_preflight_reports_missing_tools_and_env_without_printing_secret_values(monkeypatch):
    for name in (
        "DECISION_SOR_PLATFORM_URL",
        "DECISION_SOR_SERVICE_URL",
        "DECISION_SOR_ADMIN_DATABASE_URL",
        "DECISION_SOR_PLATFORM_ROLE",
        "DATABASE_URL",
        "SAHOOL_AGENT_TOKEN",
        "FIELD_SERVICE_URL",
        "TENANT_A",
        "TENANT_B",
        "FIELD_A",
        "KG_SERVICE_URL",
        "KG_TENANT_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    body = mod.preflight(SHA)
    assert body["classification"] == "FAILED"
    assert "missing_tool:psql" in body["findings"]
    assert "missing_env:SAHOOL_AGENT_TOKEN" in body["findings"]
    rendered = json.dumps(body)
    assert "postgres://" not in rendered
    assert "Bearer " not in rendered


def test_preflight_binds_collection_checkout_to_exact_subject(monkeypatch):
    required = (
        "DECISION_SOR_PLATFORM_URL",
        "DECISION_SOR_SERVICE_URL",
        "DECISION_SOR_ADMIN_DATABASE_URL",
        "DECISION_SOR_PLATFORM_ROLE",
        "DATABASE_URL",
        "SAHOOL_AGENT_TOKEN",
        "FIELD_SERVICE_URL",
        "TENANT_A",
        "TENANT_B",
        "FIELD_A",
        "KG_SERVICE_URL",
        "KG_TENANT_ID",
    )
    for name in required:
        monkeypatch.setenv(name, "set")
    monkeypatch.setattr(mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(mod, "_run", lambda *a, **kw: {"returncode": 0, "output": "b" * 40})
    body = mod.preflight(SHA)
    assert body["classification"] == "FAILED"
    assert any(x.startswith("checkout_subject_sha_mismatch:") for x in body["findings"])
