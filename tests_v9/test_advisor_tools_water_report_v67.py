"""تحقّق V67 — سدّ ثغرتَي أدوات المستشار (P13): get_water_productivity + generate_report.

التقرير الخارجيّ/تدقيق P13: الأداتان مفقودتان من السجلّ. مُضافتان الآن كأداتَي **قراءة
فقط** (منخفضة الخطر، بلا تعديل، بلا موافقة) ومُعلَنتان للمزوّد (read-only allowlist).

- كلتاهما في `TOOLS` بثوابت القراءة (mutating=False, requires_approval=False, risk=low).
- كلتاهما ضمن `READ_ONLY_TOOL_NAMES` وتظهران في `build_provider_tools` بالصيغتَين.
- لا تُعدّلان حالة (صدق: تقرير/قراءة لا إرسال).

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import provider_tooling as PT  # noqa: E402
from shared.ai import tool_registry as REG  # noqa: E402

_NEW = ("get_water_productivity", "generate_report")


def test_new_tools_registered_as_read_only():
    for name in _NEW:
        spec = REG.get_tool(name)
        assert spec is not None, f"{name} يجب أن يكون في السجلّ"
        assert spec.risk == REG.RISK_LOW
        assert spec.mutating is False
        assert spec.requires_approval is False
        assert spec.capability == "can_read_field_data"


def test_new_tools_do_not_require_human_approval():
    for name in _NEW:
        assert REG.requires_human_approval(name) is False


def test_new_tools_in_provider_read_only_allowlist():
    for name in _NEW:
        assert name in PT.READ_ONLY_TOOL_NAMES


def test_new_tools_advertised_openai_and_anthropic():
    for wire in ("openai_chat", "messages"):
        tools = PT.build_provider_tools(wire)
        names = {
            (t.get("function", {}).get("name") if wire == "openai_chat" else t.get("name"))
            for t in tools
        }
        assert "get_water_productivity" in names
        assert "generate_report" in names


def test_generate_report_params_are_read_shaped():
    schema = PT._TOOL_PARAMETERS["generate_report"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"field_id", "period"}


def test_registry_still_unique_and_sized():
    names = REG.tool_names()
    assert len(names) == len(set(names))  # لا تكرار
    assert len(REG.TOOLS) >= 12


# ── V67.1: التنفيذ الفعليّ — الجالب الحيّ يُرجِع أدلّة (لا يفشل مُغلَقاً) ──────────────
def test_live_fetcher_executes_new_tools_with_evidence():
    pytest.importorskip("fastapi")  # main يستورد fastapi — يُتخطّى في بيئة الوحدة الدنيا
    from services.ai_agronomist import main as MAIN

    fetcher = MAIN._build_agent_tool_fetcher(
        field_state={"field_id": "f1", "water_deficit": 18.0},
        ai_pack={
            "imagery_timeline": {"total_dates": 12},
            "weather_history": {"x": 1},
            "readiness": "ok",
        },
        annotations={},
    )
    wp = fetcher("get_water_productivity", {"field_id": "f1"})
    assert wp["available"] is True and "water_deficit" in wp["water_productivity"]
    rep = fetcher("generate_report", {"field_id": "f1", "period": "2026-Q2"})
    assert rep["report_type"] == "read_only_field_digest"
    assert "imagery_timeline" in rep["evidence_sources"]  # أدلّة حقيقيّة من السياق


def test_live_fetcher_water_productivity_honest_when_empty():
    pytest.importorskip("fastapi")  # main يستورد fastapi — يُتخطّى في بيئة الوحدة الدنيا
    from services.ai_agronomist import main as MAIN

    fetcher = MAIN._build_agent_tool_fetcher(field_state={}, ai_pack={}, annotations={})
    wp = fetcher("get_water_productivity", {})
    # لا اختلاق: سياق فارغ ⇒ available=False + سبب صريح (لا رقم مُخترَع).
    assert wp["available"] is False and wp["note_ar"]
