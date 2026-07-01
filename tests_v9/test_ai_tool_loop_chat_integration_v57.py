"""حارس V57 — وصل Tool Calling Loop بمسار chat الحيّ.

يفرض أن حلقة الأدوات لم تعد بنية منفصلة فقط، بل أصبحت جزءاً من عقد
``/api/ai-agronomist/chat``:
- AdvisorQuery يقبل ``tool_calls``.
- ``_build_evidence_response`` يستدعي ``tool_loop.run_tool_calls``.
- السياسة تُطبَّع قبل تمرير القدرات.
- ``harness`` يعرض نتائج الأدوات وطلبات الموافقة.
- الاستجابة تعيد ``tool_calls`` و``pending_approvals`` و``tool_calls_truncated``.
- جالب الأدوات القرائيّة مبنيّ من سياق الحقل/AI Context Pack، لا من اختلاقات.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _main_module():
    # ``main`` يستورد fastapi؛ وظائف CI للوحدة/التكامل (منطق صرف على tests_v9) لا
    # تُثبّت fastapi، فنتخطّى بأمان بدل كسر الجمع. الحارس الساكن أدناه يعمل بلا استيراد.
    pytest.importorskip("fastapi")
    from services.ai_agronomist import main as M

    return M


def test_advisor_query_accepts_tool_calls_contract():
    M = _main_module()
    q = M.AdvisorQuery(
        question="افتح صورة الحقل",
        tenant_id="t",
        tool_calls=[{"tool": "get_field_state", "params": {"field_id": "f"}}],
    )
    assert q.tool_calls and q.tool_calls[0]["tool"] == "get_field_state"


def test_main_wires_tool_loop_into_chat_response_static():
    source = Path("services/ai_agronomist/main.py").read_text(encoding="utf-8")
    assert "tool_loop.run_tool_calls" in source
    assert 'allowed_capabilities=_policy.get("allowed_capabilities")' in source
    assert "normalize_policy" in source
    assert (
        "tool_calls=all_tool_calls" in source
        or 'tool_calls=tool_result.get("tool_calls")' in source
    )
    assert (
        "pending_approvals=all_pending_approvals" in source
        or 'pending_approvals=tool_result.get("pending_approvals")' in source
    )
    assert (
        '"tool_calls_truncated": bool(tool_result.get("truncated"))' in source
        or '"tool_calls_truncated": tool_result.get("truncated")' in source
    )


def test_field_tool_fetcher_returns_contextual_read_data():
    M = _main_module()
    pack = {
        "field_id": "field-1",
        "imagery_timeline": {"total_dates": 12, "ready_dates": 10},
        "weather_history": {"available": True, "summary": {"days": 730}},
        "alerts_context": {"total": 2},
        "drawing_context": {"total": 3},
        "readiness": {"complete": True},
    }
    field_state = {"field_id": "field-1", "ai_context_pack": pack, "crop": "قمح"}
    fetcher = M._build_agent_tool_fetcher(
        field_state=field_state,
        ai_pack=pack,
        annotations={"rag": [], "knowledge_graph": [], "canonical_field_state": field_state},
    )

    scene = fetcher("get_truecolor_scene", {"field_id": "field-1", "date": "2026-06-01"})
    assert scene["index"] == "truecolor"
    assert scene["imagery_timeline"]["total_dates"] == 12

    weather = fetcher("get_weather_history", {"field_id": "field-1", "days": 730})
    assert weather["weather_history"]["summary"]["days"] == 730

    ui = fetcher("open_map_layer", {"field_id": "field-1", "layer": "truecolor"})
    assert ui["ui_action"] == "open_map_layer"
    assert ui["layer"] == "truecolor"
