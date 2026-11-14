"""اختبارات تحليل جودة ماء الريّ (SAR/RSC/EC) — عتبات مرجعيّة موثَّقة.

فجوة تغطية (مراجعة الجولة ٣): وحدة نقيّة تحكم تصنيف خطر الملوحة/الصوديوم/القلويّة
بعتبات مُوثَّقة (USSL/USDA Bull.197/FAO-29/Eaton 1950) — كانت بلا اختبار. هنا نقفل
الصيغ والحدود وصدق «غير محسوب عند نقص مدخل».
"""

import math

import pytest
from core.irrigation_water_analysis import (
    WaterSample,
    analyze_water_sample,
    classify_ec,
    classify_rsc,
    classify_sar,
    compute_rsc,
    compute_sar,
)

pytestmark = pytest.mark.unit

# ─── compute_sar = Na/√((Ca+Mg)/2) ───────────────────────────────────────


def test_compute_sar_formula():
    # na=10, (ca+mg)/2 = 2 ⇒ 10/√2 = 7.07
    assert compute_sar(10, 2, 2) == round(10 / math.sqrt(2), 2) == 7.07


def test_compute_sar_none_on_missing_or_zero_denom():
    assert compute_sar(None, 2, 2) is None
    assert compute_sar(10, 0, 0) is None  # صدق: لا قسمة على صفر


# ─── compute_rsc = (CO3+HCO3) − (Ca+Mg) ──────────────────────────────────


def test_compute_rsc_formula_and_missing():
    assert compute_rsc(1, 5, 1, 1) == 4.0
    assert compute_rsc(0, 2, None, 1) is None


# ─── تصنيف SAR (USSL): <10 منخفض · <18 متوسّط · <26 مرتفع · ≥26 جدّاً ─────


def test_classify_sar_bands():
    assert classify_sar(compute_sar(8, 2, 2))["class"] == "low"  # 5.66
    assert classify_sar(compute_sar(20, 2, 2))["class"] == "medium"  # 14.14
    assert classify_sar(compute_sar(30, 2, 2))["class"] == "high"  # 21.21
    assert classify_sar(compute_sar(40, 2, 2))["class"] == "very_high"  # 28.28
    assert classify_sar(None)["class"] is None


# ─── تصنيف RSC (USDA Bull.197): <1.25 آمن · ≤2.50 هامشي · >2.50 غير مناسب ─


def test_classify_rsc_bands():
    assert classify_rsc(0.5)["class"] == "safe"
    assert classify_rsc(2.0)["class"] == "marginal"
    assert classify_rsc(2.50)["class"] == "marginal"  # الحدّ مشمول
    assert classify_rsc(4.0)["class"] == "unsuitable"


# ─── تصنيف EC (FAO-29): <0.7 منخفض · ≤3.0 متوسّط · >3.0 شديد ─────────────


def test_classify_ec_bands():
    assert classify_ec(0.5)["class"] == "low"
    assert classify_ec(2.0)["class"] == "moderate"
    assert classify_ec(5.0)["class"] == "severe"
    assert classify_ec(None)["class"] is None


# ─── التحليل الكامل: أسوأ تصنيف يحكم + إعلان النقص ────────────────────────


def test_analyze_flags_worst_hazards_and_reports_missing():
    s = WaterSample(sample_id="w1", na=40, ca=2, mg=2, co3=1, hco3=6, ec_dsm=5.0)
    out = analyze_water_sample(s)
    # EC شديد + RSC غير مناسب + SAR مرتفع جدّاً ⇒ ثلاث رايات + غير صالح بلا معالجة.
    assert "ملوحة شديدة" in out["hazard_flags_ar"]
    assert "قلويّة عالية" in out["hazard_flags_ar"]
    assert "صوديوم مرتفع" in out["hazard_flags_ar"]
    assert out["suitable_ar"].startswith("يحتاج معالجة")
    assert out["data_complete"] is True


def test_analyze_declares_missing_inputs_no_fabrication():
    s = WaterSample(sample_id="w2", na=10, ca=2, mg=2)  # بلا co3/hco3/ec
    out = analyze_water_sample(s)
    assert out["indices"]["rsc_meq_l"] is None  # غير محسوب (لا تأليف)
    assert set(out["missing_inputs"]) >= {"hco3", "co3", "ec_dsm"}
    assert out["data_complete"] is False


# ─── حدود التصنيف بالضبط (حارس انحدار < مقابل ≤) — العتبات الموثَّقة ───────
# الاختبارات أعلاه تستخدم قيماً وسط النطاقات؛ هذه تثبّت القيمة الحدّيّة نفسها كي
# لا ينزلق `<` إلى `≤` (أو العكس) صامتاً على عتبة علميّة موثَّقة.


def test_classify_sar_exact_band_edges():
    # USSL: <10 منخفض · <18 متوسّط · <26 مرتفع · ≥26 جدّاً — الحدّ يقع في النطاق الأعلى.
    assert classify_sar(10.0)["class"] == "medium"  # 10 ليس <10 ⇒ متوسّط لا منخفض
    assert classify_sar(18.0)["class"] == "high"  # 18 ليس <18 ⇒ مرتفع لا متوسّط
    assert classify_sar(26.0)["class"] == "very_high"  # 26 ليس <26 ⇒ جدّاً لا مرتفع


def test_classify_rsc_lower_edge_inclusive_safe():
    # USDA Bull.197: <1.25 آمن — الحدّ 1.25 نفسه هامشيّ (ليس آمناً).
    assert classify_rsc(1.24)["class"] == "safe"
    assert classify_rsc(1.25)["class"] == "marginal"


def test_classify_ec_exact_band_edges():
    # FAO-29: <0.7 منخفض · ≤3.0 متوسّط · >3.0 شديد.
    assert classify_ec(0.7)["class"] == "moderate"  # 0.7 ليس <0.7 ⇒ متوسّط لا منخفض
    assert classify_ec(3.0)["class"] == "moderate"  # 3.0 مشمول في المتوسّط (≤3.0)
    assert classify_ec(3.01)["class"] == "severe"  # فوق 3.0 ⇒ شديد


# ─── المسار النظيف + درجات القيود الثلاث (FAO-29) ─────────────────────────


def test_analyze_clean_water_is_suitable_with_no_flags():
    # ماء نظيف: EC منخفض + SAR منخفض + RSC آمن ⇒ لا رايات، «صالح للريّ»، مكتمل.
    s = WaterSample(sample_id="w3", na=4, ca=3, mg=3, co3=0, hco3=1, ec_dsm=0.5)
    out = analyze_water_sample(s)
    assert out["hazard_flags_ar"] == []
    assert out["restrictions"] == []
    assert out["verdict"] == "suitable"
    assert out["suitable_ar"] == "صالح للريّ"
    assert out["data_complete"] is True


# Replaces test_analyze_mid_band_classes_do_not_raise_flags, which asserted the defect:
# moderate EC + marginal RSC + medium SAR read «صالح للريّ» with no qualification, against
# FAO-29 Table 1 (three degrees of restriction) and USSL (SAR read with EC).
_CLEAN = dict(na=1.0, ca=2.0, mg=2.0, co3=0.0, hco3=1.0, ec_dsm=1.0)  # SAR 0.71, RSC −3


def _restricted(out):
    return {(r["index"], r["degree"]) for r in out["restrictions"]}


def test_mid_band_water_is_suitable_with_restrictions_naming_each_index():
    s = WaterSample(sample_id="w4", na=20, ca=2, mg=2, co3=1, hco3=5, ec_dsm=2.0)
    out = analyze_water_sample(s)
    assert out["verdict"] == "suitable_with_restrictions"
    assert out["suitable_ar"].startswith("صالح مع قيود")
    assert out["suitable_ar"] != "صالح للريّ"
    assert out["hazard_flags_ar"] == []  # لا قيد شديد ⇒ لا «يحتاج معالجة»
    assert _restricted(out) == {
        ("ec_dsm", "slight_to_moderate"),
        ("sar", "slight_to_moderate"),
        ("rsc_meq_l", "slight_to_moderate"),
    }
    assert len(out["restriction_flags_ar"]) == 3


@pytest.mark.parametrize("ec", [0.7, 2.0, 3.0])
def test_moderate_salinity_alone_is_a_restriction(ec):
    out = analyze_water_sample(WaterSample(sample_id="w", **{**_CLEAN, "ec_dsm": ec}))
    assert out["verdict"] == "suitable_with_restrictions"
    assert _restricted(out) == {("ec_dsm", "slight_to_moderate")}
    salinity = out["classification"]["salinity"]
    assert salinity["degree"] == "slight_to_moderate"


@pytest.mark.parametrize("hco3", [5.25, 6.0, 6.5])  # RSC = HCO3 − 4: 1.25 · 2.0 · 2.5
def test_marginal_rsc_alone_is_a_restriction(hco3):
    out = analyze_water_sample(WaterSample(sample_id="w", **{**_CLEAN, "hco3": hco3}))
    assert out["classification"]["alkalinity_rsc"]["class"] == "marginal"
    assert out["verdict"] == "suitable_with_restrictions"
    assert ("rsc_meq_l", "slight_to_moderate") in _restricted(out)


def _sar_sample(sar, ec):
    return WaterSample(
        sample_id="w", na=sar * math.sqrt(2), ca=2.0, mg=2.0, co3=0.0, hco3=1.0, ec_dsm=ec
    )


@pytest.mark.parametrize(
    "sar,ec,degree",
    [
        # FAO-29 Table 1 infiltration: the same SAR is graded by ECw.
        (12.0, 3.0, "none"),  # row 12–20: ECw > 2.9
        (12.0, 2.0, "slight_to_moderate"),  # 2.9 ≥ ECw ≥ 1.3
        (12.0, 1.0, "severe"),  # ECw < 1.3
        (8.0, 2.0, "none"),  # row 6–12: ECw > 1.9
        (8.0, 1.0, "slight_to_moderate"),
        (8.0, 0.4, "severe"),  # ECw < 0.5
        (25.0, 5.5, "none"),  # row 20–40: ECw > 5.0
        (25.0, 4.0, "slight_to_moderate"),
    ],
)
def test_infiltration_grades_sar_by_ecw_band(sar, ec, degree):
    out = analyze_water_sample(_sar_sample(sar, ec))
    infil = out["classification"]["infiltration_fao29"]
    assert infil["degree"] == degree
    assert infil["standard"] == "FAO-29 Table 1"


def test_medium_sar_restriction_depends_on_ecw_not_sar_alone():
    # USSL «medium» SAR 14 in both; only the low-salinity water carries an infiltration
    # restriction from sodium (FAO-29 row 12–20: none above ECw 2.9).
    saline = analyze_water_sample(_sar_sample(14.0, 2.95))
    fresh = analyze_water_sample(_sar_sample(14.0, 2.0))
    assert saline["classification"]["sodicity_sar"]["class"] == "medium"
    assert fresh["classification"]["sodicity_sar"]["class"] == "medium"
    assert ("sar", "slight_to_moderate") not in _restricted(saline)
    assert ("sar", "slight_to_moderate") in _restricted(fresh)


def test_severe_infiltration_from_sodium_needs_treatment():
    out = analyze_water_sample(_sar_sample(8.0, 0.4))
    assert out["verdict"] == "needs_treatment"
    assert ("sar", "severe") in _restricted(out)


def test_low_salinity_infiltration_without_sodium_is_an_advisory_not_a_restriction():
    # SAR < 3, ECw 0.5: FAO-29 reads slight-to-moderate from the low salt content alone.
    # Treating it as a restriction would leave no water at «no restriction» (salinity
    # needs ECw < 0.7, infiltration needs ECw > 0.7), so it is reported, not counted.
    out = analyze_water_sample(_sar_sample(0.7, 0.5))
    infil = out["classification"]["infiltration_fao29"]
    assert infil["degree"] == "slight_to_moderate"
    assert infil["sodium_attributable"] is False
    assert out["verdict"] == "suitable"
    assert out["advisories_ar"]


def test_moderate_restriction_with_an_unassessed_axis_is_insufficient_data():
    out = analyze_water_sample(WaterSample(sample_id="w", ec_dsm=2.0))
    assert out["verdict"] == "insufficient_data"
    assert ("ec_dsm", "slight_to_moderate") in _restricted(out)  # still visible
