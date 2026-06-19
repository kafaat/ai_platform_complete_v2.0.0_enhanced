"""اختبار Advisor Context Binding: حقن الحالة القانونيّة في سياق سؤال المستشار.

يثبت أنّ bind_field_context (دالّة نقيّة) يربط جواب المستشار بمصدر الحقيقة الواحد
(Canonical Field State) بصدق: لا تلفيق، لا دهس سياق العميل، None ⇒ بلا تغيير.
نواة نقيّة بلا خدمات.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
SUPERVISOR = os.path.join(ROOT, "services/supervisor-agent")
SUPERVISOR_MAIN = os.path.join(SUPERVISOR, "main.py")


@pytest.fixture(scope="module")
def sup_mod():
    # تحميل main.py الخاصّ بـsupervisor باسم فريد عبر importlib (عزل تضارب «main»).
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    added = SUPERVISOR not in sys.path
    if added:
        sys.path.insert(0, SUPERVISOR)
    try:
        spec = importlib.util.spec_from_file_location(
            "sahool_supervisor_main_advisor_test", SUPERVISOR_MAIN
        )
        sup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sup)
        yield sup
    finally:
        if added and SUPERVISOR in sys.path:
            sys.path.remove(SUPERVISOR)


_STATE = {
    "validity": "valid",
    "execution_mode": "advisory",
    "confidence_level": "medium",
    "remote_sensing": {"available": True, "ndvi_mean": 0.62, "ndvi_date": "2026-06-05"},
    "inputs": {"weather_age_hours": 3.0},
}


def test_binds_state_and_flattens(sup_mod):
    out = sup_mod.bind_field_context({}, _STATE)
    assert out["field_state"] == _STATE
    assert out["ndvi_mean"] == 0.62
    assert out["weather_age_hours"] == 3.0


def test_no_fabrication_when_unavailable(sup_mod):
    state = {"validity": "valid", "remote_sensing": {"available": False}, "inputs": {}}
    out = sup_mod.bind_field_context({}, state)
    assert "ndvi_mean" not in out  # لا تلفيق حين لا قيمة
    assert out["field_state"] is state


def test_preserves_client_context(sup_mod):
    out = sup_mod.bind_field_context({"crop": "maize", "ndvi_mean": 0.9}, _STATE)
    assert out["crop"] == "maize"
    assert out["ndvi_mean"] == 0.9  # setdefault لا يدهس ما أرسله العميل


def test_none_state_returns_copy_unchanged(sup_mod):
    src = {"crop": "wheat"}
    out = sup_mod.bind_field_context(src, None)
    assert out == {"crop": "wheat"}
    assert out is not src  # نسخة لا الأصل (لا أثر جانبيّ)


def test_none_context_safe(sup_mod):
    out = sup_mod.bind_field_context(None, None)
    assert out == {}
