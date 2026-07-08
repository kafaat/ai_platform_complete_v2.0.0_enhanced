"""حارس (M1) — مخطّطات أدوات المزوّد تُعلن ``required`` صراحةً وتتّسق مع السجلّ الحيّ.

يوجَّه النموذج من البداية لإرسال tool calls كاملة (لا اعتماد على رفض الـharness وحده):
- كلّ أداة في المسار الحيّ (``shared/ai/tool_schema.tool_definitions``) تحمل ``required`` قائمةً.
- كلّ أداة في ``provider_tooling`` (الصيغتان) تحمل ``required`` يتضمّن ``field_id``.
- **لا انحراف:** ``required`` في ``provider_tooling`` يطابق عقد السجلّ الحيّ لكلّ أداة مشتركة.
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
from shared.ai import tool_schema as TS  # noqa: E402


def _live_defs() -> list[dict]:
    caps = sorted({t.capability for t in REG.TOOLS})
    return TS.tool_definitions(caps)


def _live_required_by_name() -> dict[str, set[str]]:
    return {d["name"]: set(d["parameters"].get("required", [])) for d in _live_defs()}


def test_live_tool_schemas_all_declare_required_list():
    defs = _live_defs()
    assert defs, "يجب أن تتوفّر تعريفات أدوات حيّة"
    for d in defs:
        req = d["parameters"].get("required")
        assert isinstance(req, list), f"{d['name']} بلا قائمة required في المخطّط الحيّ"
    # أداة الحقل الأساسيّة يجب أن تُلزِم field_id (لا استدعاء بلا حقل).
    assert "field_id" in _live_required_by_name().get("get_field_state", set())


def test_provider_tooling_schemas_declare_required_with_field_id():
    for wire in ("openai_chat", "messages"):
        for tool in PT.build_provider_tools(wire):
            params = (
                tool["function"]["parameters"] if wire == "openai_chat" else tool["input_schema"]
            )
            name = tool["function"]["name"] if wire == "openai_chat" else tool["name"]
            req = params.get("required")
            assert isinstance(req, list) and "field_id" in req, (
                f"{name} ({wire}) بلا required.field_id"
            )


def test_provider_tooling_required_matches_live_registry_contract():
    live = _live_required_by_name()
    for name in PT.READ_ONLY_TOOL_NAMES:
        if name not in live:
            continue  # أداة غير موجودة في السجلّ الحيّ — خارج نطاق فحص الاتّساق.
        pt_req = set(PT._TOOL_PARAMETERS[name].get("required", []))
        assert pt_req == live[name], (
            f"انحراف required لـ{name}: provider={pt_req} live={live[name]}"
        )


def test_index_timeline_requires_index_and_days():
    # المؤشّر والنافذة إلزاميّان في السجلّ الحيّ — يجب أن ينعكسا في provider_tooling.
    assert set(PT._TOOL_PARAMETERS["get_index_timeline"]["required"]) == {
        "field_id",
        "index",
        "days",
    }
