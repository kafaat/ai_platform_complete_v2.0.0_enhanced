"""اختبارات الذكاء الاقتصاديّ (core.economic_intelligence) — المرحلة C، الشريحة 10.

نقيّة وحتميّة ⇒ `unit`. تثبّت: تحويل المم→م³ مع المساحة، حساب التكلفة المُتجنَّبة مع
الوحدة، الصدق الصارم (None + ملاحظة عند غياب المدخلات)، والعملة.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from core.economic_intelligence import summarize_economics  # noqa: E402


def _impact(**kw):
    base = {"water_saved_mm": 10.0, "executed": 5, "success_rate": 0.8}
    base.update(kw)
    return base


def test_volume_and_cost_with_full_inputs():
    # 10مم × 4ها × 10 = 400م³ ؛ × 0.5 = 200 تكلفة متجنَّبة
    e = summarize_economics(_impact(), area_ha=4.0, water_cost_per_m3=0.5, currency="YER")
    assert e.water_saved_m3 == 400.0
    assert e.water_cost_avoided == 200.0
    assert e.currency == "YER"
    assert e.executed_decisions == 5
    assert e.notes_ar is None


def test_no_area_means_no_volume_with_note():
    e = summarize_economics(_impact(), water_cost_per_m3=0.5)
    assert e.water_saved_m3 is None
    assert e.water_cost_avoided is None  # لا حجم ⇒ لا قيمة
    assert any("المساحة" in n for n in e.notes_ar)


def test_no_cost_means_no_value_with_note():
    e = summarize_economics(_impact(), area_ha=4.0)
    assert e.water_saved_m3 == 400.0
    assert e.water_cost_avoided is None
    assert any("تكلفة الوحدة" in n for n in e.notes_ar)


def test_zero_water_saved():
    e = summarize_economics(_impact(water_saved_mm=0.0), area_ha=4.0, water_cost_per_m3=0.5)
    assert e.water_saved_m3 == 0.0
    assert e.water_cost_avoided == 0.0


def test_default_currency():
    e = summarize_economics(_impact())
    assert e.currency == "YER"


def test_serializable():
    import json

    e = summarize_economics(_impact(), area_ha=2.0, water_cost_per_m3=1.0)
    blob = json.dumps(e.to_dict(), ensure_ascii=False)
    parsed = json.loads(blob)
    assert parsed["water_saved_m3"] == 200.0
    assert parsed["water_cost_avoided"] == 200.0
