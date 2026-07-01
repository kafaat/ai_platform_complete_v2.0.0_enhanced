"""حارس ركيزة وكيل الذكاء الزراعيّ (V55 — Agricultural Agent Harness).

يفرض سلامة العقود الخلفيّة للركيزة:
- سجلّ الأدوات مُحكَم (خطورة/قدرة قانونيّة، العالية تحتاج موافقة، المُعدِّلة ليست low).
- مصفوفة القدرات مغلقة + التطبيع fail-closed.
- عقد التدقيق يشتقّ الخطورة/القدرة من السجلّ ويُنقّح الأسرار.
- جدول المستأجِر (ai_agronomist) متطابق مع عقد القدرات + ترحيل v125 موجود ومُدرَج.

منطق صرف بلا قاعدة/تنفيذ (``-m unit``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.ai import capabilities as CAP  # noqa: E402
from shared.ai import tool_audit as AUDIT  # noqa: E402
from shared.ai import tool_registry as REG  # noqa: E402


def _load(rel_path: str, mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    assert spec and spec.loader, f"cannot load {rel_path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


TP = _load("services/ai_agronomist/tenant_policies.py", "sahool_tenant_policies_v55")


# ── سجلّ الأدوات ───────────────────────────────────────────────────────────
def test_registry_is_well_formed():
    names = [t.name for t in REG.TOOLS]
    assert len(names) == len(set(names)), "أسماء أدوات مكرّرة"
    assert len(REG.TOOLS) >= 12
    for t in REG.TOOLS:
        assert t.risk in REG.RISK_LEVELS, t.name
        assert t.capability in CAP.CAPABILITIES, t.name
        assert isinstance(t.params, dict), t.name
        # ثابت الحوكمة: العالية تحتاج موافقة؛ المُعدِّلة ليست low؛ القراءة بلا موافقة.
        if t.risk == REG.RISK_HIGH:
            assert t.requires_approval, f"عالية بلا موافقة: {t.name}"
        if t.mutating:
            assert t.risk != REG.RISK_LOW, f"مُعدِّلة low: {t.name}"
        else:
            assert not t.requires_approval, f"قراءة تحتاج موافقة: {t.name}"


def test_registry_covers_all_risk_tiers():
    for risk in REG.RISK_LEVELS:
        assert REG.tools_by_risk(risk), f"لا أداة بخطورة {risk}"


def test_read_tools_use_read_capabilities():
    read_caps = {CAP.CAN_READ_FIELD_DATA, CAP.CAN_READ_HISTORICAL_IMAGERY}
    for t in REG.TOOLS:
        if not t.mutating:
            assert t.capability in read_caps, t.name


def test_construction_rejects_invalid_tool():
    with pytest.raises(ValueError):
        REG.ToolSpec("bad", "x", "high", CAP.CAN_CREATE_TASKS, True, False)  # high بلا موافقة
    with pytest.raises(ValueError):
        REG.ToolSpec("bad2", "x", "low", "not_a_capability", False, False)  # قدرة مجهولة


def test_requires_human_approval_fail_closed():
    assert REG.requires_human_approval("send_recommendation") is True
    assert REG.requires_human_approval("get_field_state") is False
    assert REG.requires_human_approval("unknown_tool") is True  # مجهولة ⇒ مطلوبة


# ── مصفوفة القدرات ─────────────────────────────────────────────────────────
def test_capabilities_closed_set_and_defaults():
    assert len(CAP.CAPABILITIES) == len(set(CAP.CAPABILITIES)) == 11
    assert set(CAP.DEFAULT_CAPABILITIES) <= set(CAP.CAPABILITIES)
    # الافتراضيّ قراءة فقط (لا قدرة مُعدِّلة).
    assert not (set(CAP.DEFAULT_CAPABILITIES) & CAP.MUTATING_CAPABILITIES)


def test_capability_normalize_fail_closed():
    assert CAP.normalize_capabilities(None) == CAP.DEFAULT_CAPABILITIES
    assert CAP.normalize_capabilities(["can_read_field_data", "bogus"]) == (
        CAP.CAN_READ_FIELD_DATA,
    )
    assert CAP.has_capability(["can_create_tasks"], CAP.CAN_CREATE_TASKS)
    assert not CAP.has_capability(["bogus"], CAP.CAN_CREATE_TASKS)


# ── عقد التدقيق ────────────────────────────────────────────────────────────
def test_audit_record_derives_risk_from_registry():
    rec = AUDIT.build_audit_record(
        tool_name="send_recommendation",
        params={"field_id": "f1", "recommendation_id": "r1"},
        tenant_id="t1",
        actor="user:1",
        outcome=AUDIT.OUTCOME_PENDING_APPROVAL,
        timestamp="2026-07-01T00:00:00Z",
    )
    assert rec["risk"] == "high"
    assert rec["requires_approval"] is True
    assert rec["known_tool"] is True
    assert rec["outcome"] == "pending_approval"


def test_audit_unknown_tool_is_fail_closed():
    rec = AUDIT.build_audit_record(
        tool_name="mystery",
        params=None,
        tenant_id="t1",
        actor="ai",
        outcome="weird",  # غير قانونيّ ⇒ failed
        timestamp="2026-07-01T00:00:00Z",
    )
    assert rec["known_tool"] is False
    assert rec["risk"] == "high" and rec["requires_approval"] is True
    assert rec["outcome"] == AUDIT.OUTCOME_FAILED


def test_audit_redacts_secrets_and_identifiers():
    red = AUDIT.redact_params(
        {
            "api_token": "SECRET123",
            "note": "راسلني a@b.com المعرّف 12345678-1234-1234-1234-123456789abc",
            "days": 730,
        }
    )
    assert red["api_token"] == "[redacted]"
    assert "a@b.com" not in red["note"] and "[redacted-email]" in red["note"]
    assert "12345678-1234-1234-1234-123456789abc" not in red["note"]
    assert red["days"] == 730


# ── تطابق جدول المستأجِر مع العقد + الترحيل ────────────────────────────────
def test_tenant_capabilities_match_contract():
    assert tuple(TP.AGENT_CAPABILITIES) == CAP.CAPABILITIES
    assert tuple(TP.DEFAULT_AGENT_CAPABILITIES) == CAP.DEFAULT_CAPABILITIES
    # التطبيع في مخزن السياسة fail-closed مثل العقد.
    assert TP.normalize_capabilities(["can_create_tasks", "bogus"]) == ["can_create_tasks"]
    assert TP.normalize_policy({})["allowed_capabilities"] == list(CAP.DEFAULT_CAPABILITIES)


def test_migration_v125_exists_and_registered():
    sql = (ROOT / "migrations/v125_tenant_ai_capabilities.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE tenant_ai_policies" in sql
    assert "allowed_capabilities" in sql
    assert "ADD COLUMN IF NOT EXISTS" in sql
    manifest = (ROOT / "migrations/MANIFEST.txt").read_text(encoding="utf-8")
    assert "v125_tenant_ai_capabilities.sql" in manifest
