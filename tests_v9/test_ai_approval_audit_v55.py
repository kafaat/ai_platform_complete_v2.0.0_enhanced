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


# ─── D04 من التدقيق الموحَّد (2026-09-22) ─────────────────────────────────────


def test_a_secret_nested_below_the_first_level_is_redacted():
    """D04-أ — كان التنقيحُ سطحيّاً، فـ`params.nested.api_key` يبقى في السجلّ.

    ولم تُستعمَل أسرارٌ حقيقيّةٌ في هذا القياس — وسمٌ صناعيٌّ يكفي لإثبات المسار.
    """
    approval = _load("services/ai_agronomist/approval.py", "approval_d04_nested")

    out = approval._redact(
        {
            "api_key": "TOP",
            "nested": {"api_key": "NESTED-SECRET", "ok": 1},
            "items": [{"password": "DEEP-SECRET"}],
        }
    )

    assert out["api_key"] == "[redacted]"
    assert out["nested"]["api_key"] == "[redacted]", "سرٌّ في الطبقة الثانية بقي مكشوفاً"
    assert out["nested"]["ok"] == 1, "التنقيحُ ابتلع قيمةً بريئة"
    assert out["items"][0]["password"] == "[redacted]", "سرٌّ داخل قائمةٍ بقي مكشوفاً"


def test_two_different_ids_do_not_collapse_to_one_input_hash():
    """D04-ب — أخطرُها: بصمةٌ واحدةٌ لمدخلين **مختلفين**.

    UUIDان مختلفان كانا يصيران `[redacted-id]` كلاهما **قبل** التجزئة، فتتساوى
    البصمتان. وليس ذاك تصادماً في SHA-256 بل فقدانَ دلالةٍ قبلها — والبصمةُ
    تُستعمَل لإثبات أنّ الموافقةَ مربوطةٌ بالكيان نفسِه.
    """
    approval = _load("services/ai_agronomist/approval.py", "approval_d04_hash")

    a = {"field_id": "11111111-1111-1111-1111-111111111111"}
    b = {"field_id": "22222222-2222-2222-2222-222222222222"}

    assert approval.input_hash(a) != approval.input_hash(b), (
        "مدخلان مختلفان لهما البصمةُ نفسُها — الموافقةُ غيرُ مربوطةٍ بكيانها"
    )
    # وثباتُ البصمة على المدخل نفسِه شرطٌ مقابل: وإلّا لم تصلح للربط أصلاً.
    assert approval.input_hash(a) == approval.input_hash(dict(a))


def test_the_hash_does_not_leak_the_input_and_keys_change_it(monkeypatch):
    """والبصمةُ لا تُعيد المدخل، ومفتاحٌ خادميٌّ يمنع تخمينَ معرّفٍ حسّاسٍ بقاموس."""
    approval = _load("services/ai_agronomist/approval.py", "approval_d04_hmac")
    params = {"field_id": "11111111-1111-1111-1111-111111111111"}

    monkeypatch.delenv("SAHOOL_AGENT_TOKEN", raising=False)
    bare = approval.input_hash(params)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "server-side-key")
    keyed = approval.input_hash(params)

    assert "1111" not in bare and "1111" not in keyed, "البصمةُ تُعيد المدخل"
    assert bare != keyed, "المفتاحُ الخادميُّ لا يُغيّر البصمة — فلا يمنع التخمين"


def test_a_secret_in_the_result_is_redacted_before_the_store():
    """D04-ج — كانت `result` تُحفَظ خاماً، فبقي `authorization` رغم تنقيح `params`."""
    approval = _load("services/ai_agronomist/approval.py", "approval_d04_result")
    saved: list = []

    ok = approval.emit_audit(
        {
            "tool": "t",
            "params": {"field_id": "f-1"},
            "result": {"authorization": "Bearer LEAK", "nested": {"token": "ALSO-LEAK"}},
        },
        saved.append,
    )

    assert ok and saved
    stored = saved[0]["result"]
    assert stored["authorization"] == "[redacted]", "سرُّ النتيجة حُفِظ خاماً"
    assert stored["nested"]["token"] == "[redacted]"
