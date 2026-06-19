"""اختبار عقد اكتمال السياق في Guardrails (fail-closed): يرفض السياق الناقص بدل
حوكمة شكليّة. يثبت: الدالّة النقيّة contract_violations، وأنّ engine.validate يرفض
الناقص (incomplete_context) ويمرّر الكامل للطبقات. نواة بلا شبكة/قاعدة.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
GR = os.path.join(ROOT, "services/guardrails-engine")
GR_MAIN = os.path.join(GR, "main.py")


@pytest.fixture(scope="module")
def gr_mod():
    pytest.importorskip("fastapi")
    pytest.importorskip("jwt")
    added = GR not in sys.path
    if added:
        sys.path.insert(0, GR)
    try:
        spec = importlib.util.spec_from_file_location("sahool_guardrails_main_under_test", GR_MAIN)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        yield m
    finally:
        if added and GR in sys.path:
            sys.path.remove(GR)


def test_contract_violations_pure(gr_mod):
    cv = gr_mod.contract_violations
    # مبيد بلا جرعة ⇒ ناقص (الجرعة الصفريّة الصامتة خطر سلامة)
    assert cv("pesticide", {"chemical": "x"}, {}) == ["action_data.dosage_kg_ha"]
    # اقتصاديّ بلا إيراد سنويّ ⇒ ناقص (يُعطّل كلّ الفحص الاقتصاديّ)
    assert cv("loan", {"loan_amount_usd": 5000}, {}) == ["farm_context.annual_revenue_usd"]
    # كامل ⇒ لا نقص
    assert cv("pesticide", {"chemical": "x", "dosage_kg_ha": 2.0}, {}) == []
    # قيمة 0 صريحة مشروعة (ليست نقصاً)
    assert cv("irrigation", {"water_m3": 0}, {}) == []
    # نوع بلا عقد ⇒ لا نقص (لا يكسر harvest/fertilization)
    assert cv("harvest", {}, {}) == []


def test_validate_rejects_incomplete(gr_mod):
    eng = gr_mod.SAHOOLGuardrailsEngine()
    req = gr_mod.GuardrailsRequest(
        action_type="pesticide",
        action_data={"chemical": "glyphosate"},  # بلا dosage_kg_ha
        farm_context={"field_id": "f1"},
        user_id="u1",
        tenant_id="t1",
    )
    res = asyncio.run(eng.validate(req))
    assert res.allowed is False
    assert res.overall_risk == "HIGH"
    assert res.tier_checks[0]["findings"][0]["rule"] == "incomplete_context"


def test_validate_passes_complete_past_contract(gr_mod):
    # سياق كامل ⇒ لا يُرفَض بعقد الاكتمال (يصل للطبقات الفعليّة).
    eng = gr_mod.SAHOOLGuardrailsEngine()
    req = gr_mod.GuardrailsRequest(
        action_type="irrigation",
        action_data={"water_m3": 100.0},
        farm_context={"field_id": "f1", "field_area_ha": 2.0, "water_source": "groundwater"},
        user_id="u1",
        tenant_id="t1",
    )
    res = asyncio.run(eng.validate(req))
    rules = [f.get("rule") for c in res.tier_checks for f in c.get("findings", [])]
    assert "incomplete_context" not in rules
