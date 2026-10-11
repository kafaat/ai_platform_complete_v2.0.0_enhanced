"""اختبارات الذكاء الاقتصاديّ (core.economic_intelligence) — المرحلة C، الشريحة 10.

نقيّة وحتميّة ⇒ `unit`. تثبّت: تحويل المم→م³ مع المساحة، تسعير الفرق (لا وفراً) مع
الوحدة، الصدق الصارم (None + ملاحظة عند غياب المدخلات)، والعملة.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from core.economic_intelligence import summarize_economics  # noqa: E402


def _impact(**kw):
    base = {"requested_minus_applied_mm": 10.0, "executed": 5, "success_rate": 0.8}
    base.update(kw)
    return base


def test_volume_and_cost_with_full_inputs():
    # 10مم × 4ها × 10 = 400م³ ؛ × 0.5 = 200 قيمةٌ اسميّة للفرق (لا وفر)
    e = summarize_economics(_impact(), area_ha=4.0, water_cost_per_m3=0.5, currency="YER")
    assert e.requested_minus_applied_m3 == 400.0
    assert e.requested_minus_applied_value == 200.0
    assert e.currency == "YER"
    assert e.executed_decisions == 5
    # المدخلاتُ كاملة، ويبقى التنبيهُ الوحيد أنّ الفرق ليس وفراً.
    assert e.notes_ar == [
        "الفرقُ بين المطلوب والمُنفَّذ ليس وفراً مثبتاً ولا تكلفةً متجنَّبة (savings_claim)."
    ]


def test_no_area_means_no_volume_with_note():
    e = summarize_economics(_impact(), water_cost_per_m3=0.5)
    assert e.requested_minus_applied_m3 is None
    assert e.requested_minus_applied_value is None  # لا حجم ⇒ لا قيمة
    assert any("المساحة" in n for n in e.notes_ar)


def test_no_cost_means_no_value_with_note():
    e = summarize_economics(_impact(), area_ha=4.0)
    assert e.requested_minus_applied_m3 == 400.0
    assert e.requested_minus_applied_value is None
    assert any("تكلفة الوحدة" in n for n in e.notes_ar)


def test_zero_water_saved():
    e = summarize_economics(
        _impact(requested_minus_applied_mm=0.0), area_ha=4.0, water_cost_per_m3=0.5
    )
    assert e.requested_minus_applied_m3 == 0.0
    assert e.requested_minus_applied_value == 0.0


def test_default_currency():
    e = summarize_economics(_impact())
    assert e.currency == "YER"


def test_serializable():
    import json

    e = summarize_economics(_impact(), area_ha=2.0, water_cost_per_m3=1.0)
    blob = json.dumps(e.to_dict(), ensure_ascii=False)
    parsed = json.loads(blob)
    assert parsed["requested_minus_applied_m3"] == 200.0
    assert parsed["requested_minus_applied_value"] == 200.0


# REQUESTED-MINUS-APPLIED-REPORTED-AS-WATER-SAVED-01 — الاستجابةُ والتقرير لا يعرضان الفرق وفراً سببيّاً.
def test_the_response_never_names_the_difference_a_saving():
    import json

    blob = json.dumps(summarize_economics(_impact(), area_ha=2.0, water_cost_per_m3=1.0).to_dict())
    for forbidden in ("water_saved", "cost_avoided", "avoided"):
        assert forbidden not in blob, forbidden


def test_the_response_declares_the_saving_not_established_with_four_separate_proofs():
    out = summarize_economics(_impact(), area_ha=2.0, water_cost_per_m3=1.0).to_dict()
    claim = out["savings_claim"]
    assert claim["status"] == "not_established"
    assert claim["basis"] == "requested_minus_applied"
    assert set(claim["evidence_required"]) == {
        "withdrawal_reduction",
        "consumption_reduction",
        "attribution",
        "economic_impact",
    }
    assert any("ليس وفراً" in n for n in out["notes_ar"])


def test_millimetres_summed_across_fields_are_not_multiplied_by_one_area():
    e = summarize_economics(_impact(), area_ha=4.0, water_cost_per_m3=0.5, single_field=False)
    assert e.requested_minus_applied_m3 is None
    assert e.requested_minus_applied_value is None
    assert any("عبر حقول" in n for n in e.notes_ar)
