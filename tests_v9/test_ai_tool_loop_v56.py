"""حارس حلقة الأدوات الحيّة + تعريفات function-calling (V56).

يفرض:
- تعريفات الأدوات **مُصفّاة بالقدرة** (النموذج لا يرى ما لا يملكه المستأجِر) + JSON Schema.
- حلقة التنفيذ محوكَمة: قراءة مسموحة تُنفَّذ · مُعدِّلة/عالية ⇒ طلب موافقة (لا تنفيذ) ·
  مرفوضة لا تستدعي الجالب · سقف عدد الاستدعاءات · تدقيق لكلّ استدعاء.

منطق صرف (``-m unit``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import tool_loop as LOOP  # noqa: E402
from shared.ai import tool_schema as SCH  # noqa: E402

_TS = "2026-07-01T00:00:00Z"
_READ_CAPS = ["can_read_field_data", "can_read_historical_imagery"]


# ── تعريفات function-calling مُصفّاة بالقدرة ────────────────────────────────
def test_tool_definitions_are_capability_filtered():
    names = SCH.tool_names_for(_READ_CAPS)
    assert "get_field_state" in names  # قراءة ممنوحة
    assert "create_scouting_task" not in names  # can_create_tasks غير ممنوحة
    assert "send_recommendation" not in names  # can_send_recommendations غير ممنوحة
    # مستأجِر بلا قدرات ⇒ افتراضيّ قرائيّ فقط (fail-closed).
    assert "get_field_state" in SCH.tool_names_for(None)
    assert "export_enterprise_data" not in SCH.tool_names_for(None)


def test_tool_definition_shape_is_valid_function_calling():
    d = next(d for d in SCH.tool_definitions(_READ_CAPS) if d["name"] == "get_index_timeline")
    assert d["description"]
    assert d["parameters"]["type"] == "object"
    assert d["parameters"]["properties"]["days"]["type"] == "integer"
    assert "field_id" in d["parameters"]["required"]
    assert d["x_sahool"]["risk"] == "low"


def test_full_capabilities_expose_all_tools():
    from shared.ai.tool_registry import CAPABILITIES, TOOLS

    assert len(SCH.tool_definitions(list(CAPABILITIES))) == len(TOOLS)


# ── حلقة التنفيذ المحوكَمة ──────────────────────────────────────────────────
def _fetcher(name, params):
    return {"ok": True, "tool": name}


def test_loop_executes_read_and_defers_mutating():
    audit = []
    out = LOOP.run_tool_calls(
        [
            {"tool": "get_field_state", "params": {"field_id": "f"}},
            {"tool": "create_scouting_task", "params": {"field_id": "f", "zone": "z"}, "id": "a1"},
        ],
        allowed_capabilities=[
            "can_read_field_data",
            "can_read_historical_imagery",
            "can_create_tasks",
        ],
        fetcher=_fetcher,
        tenant_id="t",
        actor="ai",
        timestamp=_TS,
        audit_saver=audit.append,
    )
    outcomes = {r["tool"]: r["outcome"] for r in out["tool_calls"]}
    assert outcomes["get_field_state"] == "executed"
    assert outcomes["create_scouting_task"] == "pending_approval"
    assert len(out["pending_approvals"]) == 1
    assert out["pending_approvals"][0]["tool"] == "create_scouting_task"
    assert len(audit) == 2  # كلّ استدعاء دُوِّن


def test_loop_denies_without_capability_and_skips_fetcher():
    calls = {"n": 0}

    def fetcher(name, params):
        calls["n"] += 1
        return {}

    out = LOOP.run_tool_calls(
        [{"tool": "get_index_timeline", "params": {"field_id": "f", "index": "ndvi", "days": 30}}],
        allowed_capabilities=["can_read_field_data"],  # ينقص can_read_historical_imagery
        fetcher=fetcher,
        tenant_id="t",
        actor="ai",
        timestamp=_TS,
    )
    assert out["tool_calls"][0]["outcome"] == "denied"
    assert calls["n"] == 0


def test_loop_caps_number_of_calls():
    many = [{"tool": "get_field_state", "params": {"field_id": "f"}} for _ in range(20)]
    out = LOOP.run_tool_calls(
        many,
        allowed_capabilities=["can_read_field_data"],
        fetcher=_fetcher,
        tenant_id="t",
        actor="ai",
        timestamp=_TS,
        max_calls=8,
    )
    assert out["truncated"] is True
    assert len(out["tool_calls"]) == 8


def test_loop_empty_is_safe():
    out = LOOP.run_tool_calls(
        None, allowed_capabilities=None, fetcher=_fetcher, tenant_id="t", actor="ai", timestamp=_TS
    )
    assert out == {"tool_calls": [], "pending_approvals": [], "truncated": False}
