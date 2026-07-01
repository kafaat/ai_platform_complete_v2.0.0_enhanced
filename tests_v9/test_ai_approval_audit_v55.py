"""حارس بوّابة الموافقة + التدقيق الدائم (V55 — المرحلة ٤).

يفرض: طلب موافقة مُنقَّح · لا موافقة مزدوجة · إدامة تدقيق best-effort آمنة · وجود
ترحيل v126 (append-only + RLS+FORCE) ومُدرَج. منطق صرف (``-m unit``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load(rel_path: str, mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    assert spec and spec.loader, f"cannot load {rel_path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


AP = _load("services/ai_agronomist/approval.py", "sahool_approval_v55")
_TS = "2026-07-01T00:00:00Z"


def _req(**kw):
    base = dict(
        request_id="req-1",
        tool_name="send_recommendation",
        params={"field_id": "f", "recommendation_id": "r"},
        tenant_id="t1",
        actor="ai",
        risk="high",
        capability="can_send_recommendations",
        requested_at=_TS,
    )
    base.update(kw)
    return AP.build_approval_request(**base)


def test_request_starts_pending_and_redacts():
    r = _req(params={"field_id": "f", "api_token": "SECRET"})
    assert r["status"] == AP.STATUS_PENDING
    assert r["params"]["api_token"] == "[redacted]"
    assert r["decided_by"] is None


def test_approve_moves_to_approved():
    r = AP.approve(_req(), approver="user:9", decided_at=_TS)
    assert r["status"] == AP.STATUS_APPROVED
    assert r["decided_by"] == "user:9" and r["decided_at"] == _TS


def test_deny_records_reason():
    r = AP.deny(_req(), approver="user:9", decided_at=_TS, reason="خارج الميزانيّة")
    assert r["status"] == AP.STATUS_DENIED
    assert r["deny_reason"] == "خارج الميزانيّة"


def test_no_double_decision():
    approved = AP.approve(_req(), approver="u", decided_at=_TS)
    with pytest.raises(ValueError):
        AP.approve(approved, approver="u2", decided_at=_TS)
    with pytest.raises(ValueError):
        AP.deny(approved, approver="u2", decided_at=_TS)


def test_emit_audit_persists_and_redacts():
    saved = []
    ok = AP.emit_audit(
        {
            "tool": "get_field_state",
            "params": {"field_id": "f", "secret": "X"},
            "outcome": "executed",
        },
        saved.append,
    )
    assert ok is True
    assert saved[0]["params"]["secret"] == "[redacted]"


def test_emit_audit_without_saver_is_noop():
    assert AP.emit_audit({"tool": "x", "params": {}}, None) is False


def test_emit_audit_saver_failure_is_safe():
    def bad(_record):
        raise RuntimeError("db down")

    assert AP.emit_audit({"tool": "x", "params": {}}, bad) is False  # لا استثناء


def test_migration_v126_append_only_rls_and_registered():
    sql = (ROOT / "migrations/v126_agent_tool_audit.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS agent_tool_audit" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql and "FORCE ROW LEVEL SECURITY" in sql
    assert "sahool_block_mutation" in sql  # append-only
    assert "BEFORE UPDATE OR DELETE" in sql
    assert "current_setting('app.current_tenant', true)" in sql
    manifest = (ROOT / "migrations/MANIFEST.txt").read_text(encoding="utf-8")
    assert "v126_agent_tool_audit.sql" in manifest
