"""اختبارات crop_market_gap (offline صرف — بلا قاعدة/شبكة).

تغطّي عقد كشف تركّز المحاصيل وفجوة السوق الإقليميّة:
  • share            — حارس القسمة على صفر (إجمالي حقول ≤ 0)
  • classify_concentration — سلوك الحدود (NONE/HIGH/LOW/MODERATE)
  • assess_crop_gap  — الإشارات الأربع + تحذير العيّنة الصغيرة + الثقة
  • regional_crop_map — تقسيم التشبّعات/الفرص + ملاحظتا الصدق والخصوصيّة

المبدأ المُتحقَّق منه: حتميّة صرفة، اتجاهات نسبيّة لا أرقام مطلقة، إعلان
نقص الثقة عند صغر العيّنة، وحقول المنصّة فقط (احترام الخصوصيّة).
"""

from core.engines.crop_market_gap import (
    HIGH_CONCENTRATION,
    LOW_CONCENTRATION,
    MIN_SAMPLE_FIELDS,
    ConcentrationLevel,
    CropConcentration,
    assess_crop_gap,
    classify_concentration,
    regional_crop_map,
)

# ─── share — حارس القسمة على صفر ─────────────────────────────────────────


def test_share_zero_guard_when_zone_empty():
    # إجمالي حقول المنطقة = 0 ⇒ لا قسمة على صفر، حصّة = 0.0
    conc = CropConcentration("wheat", "z1", field_count=0, total_fields_in_zone=0)
    assert conc.share == 0.0


def test_share_zero_guard_when_negative_total():
    # إجمالي سالب (إدخال فاسد) ⇒ يُعامَل كصفر، لا انهيار
    conc = CropConcentration("wheat", "z1", field_count=3, total_fields_in_zone=-2)
    assert conc.share == 0.0


def test_share_normal_ratio():
    conc = CropConcentration("wheat", "z1", field_count=2, total_fields_in_zone=8)
    assert conc.share == 0.25


# ─── classify_concentration — سلوك الحدود (حتمي) ─────────────────────────


def test_classify_none_when_field_count_zero():
    # لا يُزرع إطلاقاً ⇒ NONE حتّى لو الإجمالي كبير
    conc = CropConcentration("wheat", "z1", field_count=0, total_fields_in_zone=20)
    assert classify_concentration(conc) is ConcentrationLevel.NONE


def test_classify_high_at_exact_threshold():
    # حصّة = 0.40 بالضبط ⇒ HIGH (الحدّ ضمنيّ: share >= 0.40)
    conc = CropConcentration("wheat", "z1", field_count=4, total_fields_in_zone=10)
    assert conc.share == HIGH_CONCENTRATION
    assert classify_concentration(conc) is ConcentrationLevel.HIGH


def test_classify_low_at_exact_threshold():
    # حصّة = 0.10 بالضبط ⇒ LOW (الحدّ ضمنيّ: share <= 0.10)
    conc = CropConcentration("wheat", "z1", field_count=1, total_fields_in_zone=10)
    assert conc.share == LOW_CONCENTRATION
    assert classify_concentration(conc) is ConcentrationLevel.LOW


def test_classify_moderate_between_thresholds():
    # حصّة = 0.25 (بين الحدّين) ⇒ MODERATE
    conc = CropConcentration("wheat", "z1", field_count=5, total_fields_in_zone=20)
    assert conc.share == 0.25
    assert classify_concentration(conc) is ConcentrationLevel.MODERATE


def test_classify_high_above_threshold():
    conc = CropConcentration("wheat", "z1", field_count=9, total_fields_in_zone=10)
    assert classify_concentration(conc) is ConcentrationLevel.HIGH


def test_classify_low_just_below_moderate():
    # حصّة أقلّ بقليل من 0.10 ⇒ LOW (لا MODERATE)
    conc = CropConcentration("wheat", "z1", field_count=1, total_fields_in_zone=20)
    assert conc.share == 0.05
    assert classify_concentration(conc) is ConcentrationLevel.LOW


# ─── assess_crop_gap — الإشارات الأربع ───────────────────────────────────


def test_signal_saturation_on_high_concentration():
    # تركّز مرتفع ⇒ تشبّع (بغضّ النظر عن الملاءمة)
    conc = CropConcentration("wheat", "z1", field_count=6, total_fields_in_zone=10)
    out = assess_crop_gap(conc, is_suited_to_zone=True)
    assert out["signal"] == "saturation"
    assert out["concentration_level"] == "high"
    assert out["zone_share_pct"] == 60.0
    assert out["signal_ar"]


def test_signal_opportunity_when_low_and_suited():
    # تركّز منخفض + مناسب ⇒ فرصة محتملة غير مستغلّة
    conc = CropConcentration("grapes", "z1", field_count=1, total_fields_in_zone=20)
    out = assess_crop_gap(conc, is_suited_to_zone=True)
    assert out["signal"] == "opportunity"
    assert out["is_suited"] is True


def test_signal_opportunity_when_none_and_suited():
    # معدوم الزراعة لكن مناسب ⇒ فرصة (فجوة كاملة)
    conc = CropConcentration("grapes", "z1", field_count=0, total_fields_in_zone=20)
    out = assess_crop_gap(conc, is_suited_to_zone=True)
    assert out["concentration_level"] == "none"
    assert out["signal"] == "opportunity"


def test_opportunity_mentions_import_gap_when_score_high():
    # فجوة إحلال واردات إيجابيّة (>0.3) ⇒ تُذكَر في الإشارة
    conc = CropConcentration("grapes", "z1", field_count=1, total_fields_in_zone=20)
    out = assess_crop_gap(conc, is_suited_to_zone=True, market_gap_score=0.5)
    assert "إحلال واردات" in out["signal_ar"]


def test_opportunity_omits_import_gap_when_score_low():
    # فجوة ضعيفة (≤0.3) ⇒ لا تُذكَر (لا اختراع)
    conc = CropConcentration("grapes", "z1", field_count=1, total_fields_in_zone=20)
    out = assess_crop_gap(conc, is_suited_to_zone=True, market_gap_score=0.2)
    assert "إحلال واردات" not in out["signal_ar"]


def test_signal_not_suited_when_low_and_unsuited():
    # تركّز منخفض + غير مناسب ⇒ ليست فجوة فرصة
    conc = CropConcentration("rice", "z1", field_count=1, total_fields_in_zone=20)
    out = assess_crop_gap(conc, is_suited_to_zone=False)
    assert out["signal"] == "not_suited"


def test_signal_not_suited_when_none_and_unsuited():
    conc = CropConcentration("rice", "z1", field_count=0, total_fields_in_zone=20)
    out = assess_crop_gap(conc, is_suited_to_zone=False)
    assert out["signal"] == "not_suited"


def test_signal_balanced_on_moderate():
    # تركّز معتدل ⇒ سوق متوازن (الملاءمة لا تغيّر الإشارة)
    conc = CropConcentration("wheat", "z1", field_count=5, total_fields_in_zone=20)
    out = assess_crop_gap(conc, is_suited_to_zone=True)
    assert out["signal"] == "balanced"
    assert out["concentration_level"] == "moderate"


# ─── تحذير العيّنة الصغيرة + الثقة ───────────────────────────────────────


def test_low_sample_warning_present_below_threshold():
    # إجمالي حقول المنطقة < 5 ⇒ ثقة منخفضة + تحذير صريح
    conc = CropConcentration("wheat", "z1", field_count=2, total_fields_in_zone=3)
    out = assess_crop_gap(conc, is_suited_to_zone=True)
    assert conc.total_fields_in_zone < MIN_SAMPLE_FIELDS
    assert out["confidence"] == "low"
    assert "sample_warning_ar" in out
    assert out["sample_warning_ar"]


def test_low_sample_warning_absent_at_threshold():
    # إجمالي = 5 (= العتبة) ⇒ ليست عيّنة صغيرة، لا تحذير
    conc = CropConcentration("wheat", "z1", field_count=1, total_fields_in_zone=5)
    out = assess_crop_gap(conc, is_suited_to_zone=True)
    assert out["confidence"] == "moderate"
    assert "sample_warning_ar" not in out


# ─── regional_crop_map — التقسيم + الملاحظات ─────────────────────────────


def test_regional_map_partitions_saturated_and_opportunity():
    concentrations = [
        # متشبّع (60%)
        CropConcentration("wheat", "z1", field_count=6, total_fields_in_zone=10),
        # فرصة (5% + مناسب)
        CropConcentration("grapes", "z1", field_count=1, total_fields_in_zone=20),
        # متوازن (25%) ⇒ لا في التشبّع ولا في الفرص
        CropConcentration("barley", "z1", field_count=5, total_fields_in_zone=20),
        # غير مناسب (منخفض لكن غير مناسب) ⇒ not_suited
        CropConcentration("rice", "z1", field_count=1, total_fields_in_zone=20),
    ]
    suitability = {"wheat": True, "grapes": True, "barley": True, "rice": False}
    out = regional_crop_map(concentrations, suitability)

    assert out["total_crops_analysed"] == 4
    assert len(out["all_assessments"]) == 4

    saturated_ids = {a["crop_id"] for a in out["saturated_crops"]}
    opportunity_ids = {a["crop_id"] for a in out["opportunity_crops"]}
    assert saturated_ids == {"wheat"}
    assert opportunity_ids == {"grapes"}
    # barley/rice خارج كلا المجموعتين (متوازن/غير مناسب)
    assert "barley" not in saturated_ids | opportunity_ids
    assert "rice" not in saturated_ids | opportunity_ids


def test_regional_map_has_summary_and_notes():
    concentrations = [
        CropConcentration("wheat", "z1", field_count=6, total_fields_in_zone=10),
    ]
    out = regional_crop_map(concentrations, {"wheat": True})
    # الملخّص + ملاحظتا الصدق والخصوصيّة حاضرة وغير فارغة
    assert out["summary_ar"]
    assert out["honesty_note_ar"]
    assert out["privacy_note_ar"]
    # الصدق: عيّنة لا مسح شامل
    assert "عيّنة" in out["honesty_note_ar"]
    # الخصوصيّة: حقول المنصّة فقط
    assert "المنصّة" in out["privacy_note_ar"]


def test_regional_map_uses_default_suitability_false():
    # محصول غير مذكور في الملاءمة ⇒ يُعامَل كغير مناسب (افتراض حذر)
    concentrations = [
        CropConcentration("mystery", "z1", field_count=1, total_fields_in_zone=20),
    ]
    out = regional_crop_map(concentrations, suitability={})
    assert out["all_assessments"][0]["signal"] == "not_suited"
    assert out["opportunity_crops"] == []


def test_regional_map_empty_input():
    # لا محاصيل ⇒ خريطة فارغة متّسقة (لا انهيار)
    out = regional_crop_map([], {})
    assert out["total_crops_analysed"] == 0
    assert out["saturated_crops"] == []
    assert out["opportunity_crops"] == []
    assert out["summary_ar"]
