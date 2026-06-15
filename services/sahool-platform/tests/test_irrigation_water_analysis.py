"""اختبارات تحليل جودة ماء الريّ (SAR/RSC/EC) — عتبات مرجعيّة موثَّقة.

فجوة تغطية (مراجعة الجولة ٣): وحدة نقيّة تحكم تصنيف خطر الملوحة/الصوديوم/القلويّة
بعتبات مُوثَّقة (USSL/USDA Bull.197/FAO-29/Eaton 1950) — كانت بلا اختبار. هنا نقفل
الصيغ والحدود وصدق «غير محسوب عند نقص مدخل».
"""

import math

from core.irrigation_water_analysis import (
    WaterSample,
    analyze_water_sample,
    classify_ec,
    classify_rsc,
    classify_sar,
    compute_rsc,
    compute_sar,
)

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
