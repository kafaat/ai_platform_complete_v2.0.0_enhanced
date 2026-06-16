"""اختبارات api/nutrient_4r.py (offline) — قواعد 4R للتربة الكلسيّة اليمنيّة.

نواة نقيّة بلا قاعدة/شبكة/ملفّات. نتحقّق من المبدأ الحاكم "المختبر يحكم":
N إرشاديّ دوماً مع تحذير تطاير الأمونيا عند الكلسيّة/الـpH العالي؛ P محجوب
(BLOCKED) بلا تحليل Olsen-P وإلا OK/ADVISORY حسب عتبة 10ppm؛ المغذّيات
الصغرى (Fe/Zn) محجوبة بلا قيمة وإلّا تصحيح ورقي إرشاديّ؛ والخطة الكاملة
تغطّي N/P/Fe/Zn. العتبات (CaCO3≥15، pH≥7.8، Olsen-P<10) والقيم مشتقّة من الكود.
"""

import pytest
from api.nutrient_4r import (
    _CALCAREOUS_THRESHOLD,
    _HIGH_PH_THRESHOLD,
    FourRRecommendation,
    Nutrient,
    RecommendationStatus,
    SoilContext,
    full_4r_plan,
    recommend_micronutrient,
    recommend_nitrogen,
    recommend_phosphorus,
)

pytestmark = pytest.mark.unit

_AMMONIA_WARNING = "خطر تطاير الأمونيا عالٍ — تجنّب نثر اليوريا على السطح"


# ─── النيتروجين: إرشاديّ دائماً + تحذير الكلسيّة ──────────────────────────


def test_nitrogen_is_always_advisory():
    # المعدّل يحتاج هدف إنتاج/تحليل ⇒ لا توصية معدّل قاطعة، الحالة ADVISORY.
    rec = recommend_nitrogen(SoilContext(caco3_pct=20))
    assert rec.nutrient == Nutrient.N
    assert rec.status == RecommendationStatus.ADVISORY
    # المصدر يُفضّل كبريتات/نترات على اليوريا، والوضع banding تحت السطح.
    assert "اليوريا" in rec.source_ar
    assert "banding" in rec.placement_ar


def test_nitrogen_clean_soil_no_warning():
    # تربة غير كلسيّة و pH منخفض ⇒ لا تحذير تطاير.
    rec = recommend_nitrogen(SoilContext(caco3_pct=5.0, ph=7.0))
    assert rec.warnings_ar == []


def test_nitrogen_calcareous_triggers_ammonia_warning():
    rec = recommend_nitrogen(SoilContext(caco3_pct=20.0))
    assert _AMMONIA_WARNING in rec.warnings_ar


def test_nitrogen_high_ph_triggers_ammonia_warning():
    rec = recommend_nitrogen(SoilContext(ph=8.2))
    assert _AMMONIA_WARNING in rec.warnings_ar


def test_nitrogen_caco3_boundary_is_inclusive():
    # العتبة >= 15.0 ⇒ القيمة عند الحدّ نفسها تُفعّل التحذير.
    assert (
        _AMMONIA_WARNING
        in recommend_nitrogen(SoilContext(caco3_pct=_CALCAREOUS_THRESHOLD)).warnings_ar
    )
    # أقلّ بقليل لا يُفعّل.
    assert recommend_nitrogen(SoilContext(caco3_pct=_CALCAREOUS_THRESHOLD - 0.1)).warnings_ar == []


def test_nitrogen_ph_boundary_is_inclusive():
    assert _AMMONIA_WARNING in recommend_nitrogen(SoilContext(ph=_HIGH_PH_THRESHOLD)).warnings_ar
    assert recommend_nitrogen(SoilContext(ph=_HIGH_PH_THRESHOLD - 0.1)).warnings_ar == []


def test_nitrogen_none_values_default_to_non_calcareous():
    # None تُعامَل كصفر (or 0) ⇒ لا كلسيّة ولا pH عالٍ ⇒ لا تحذير.
    rec = recommend_nitrogen(SoilContext())
    assert rec.status == RecommendationStatus.ADVISORY
    assert rec.warnings_ar == []


# ─── الفوسفور: محجوب بلا تحليل، وإلّا حسب عتبة Olsen-P ─────────────────────


def test_phosphorus_blocked_without_lab_analysis():
    # absence-of-authority ⇒ BLOCKED (مبدأ حاكم).
    rec = recommend_phosphorus(SoilContext(caco3_pct=25.0))  # كلسيّة لكن بلا p_ppm
    assert rec.status == RecommendationStatus.BLOCKED
    assert rec.source_ar == "—"
    assert "تحليل" in rec.rate_ar
    assert rec.warnings_ar  # تحذير التثبيت موجود


def test_phosphorus_sufficient_is_ok_low_rate():
    # p_ppm 20 >= 10 ⇒ ليس منخفضاً ⇒ OK، ومعدّل "منخفض".
    rec = recommend_phosphorus(SoilContext(p_ppm=20.0, caco3_pct=5.0))
    assert rec.status == RecommendationStatus.OK
    assert rec.rate_ar.startswith("منخفض")
    assert "20" in rec.rate_ar
    # غير كلسيّة ⇒ لا تحذير تثبيت.
    assert rec.warnings_ar == []


def test_phosphorus_low_is_advisory_high_rate():
    # p_ppm 5 < 10 ⇒ منخفض ⇒ ADVISORY، ومعدّل "مرتفع".
    rec = recommend_phosphorus(SoilContext(p_ppm=5.0, caco3_pct=20.0))
    assert rec.status == RecommendationStatus.ADVISORY
    assert rec.rate_ar.startswith("مرتفع")
    # كلسيّة ⇒ تحذير تثبيت الحزم.
    assert any("تثبيت الفوسفور" in w for w in rec.warnings_ar)


def test_phosphorus_olsen_threshold_boundary():
    # عتبة low_p هي p_ppm < 10 ⇒ القيمة 10 بالضبط ليست منخفضة ⇒ OK.
    assert recommend_phosphorus(SoilContext(p_ppm=10.0)).status == RecommendationStatus.OK
    # أقلّ بقليل ⇒ ADVISORY.
    assert recommend_phosphorus(SoilContext(p_ppm=9.9)).status == RecommendationStatus.ADVISORY


def test_phosphorus_non_calcareous_with_value_has_no_fixation_warning():
    rec = recommend_phosphorus(SoilContext(p_ppm=5.0, caco3_pct=5.0))
    assert rec.status == RecommendationStatus.ADVISORY  # منخفض
    assert rec.warnings_ar == []  # غير كلسيّة ⇒ لا تحذير تثبيت


# ─── المغذّيات الصغرى Fe/Zn: محجوبة بلا قيمة، وإلّا تصحيح ورقي ─────────────


def test_iron_blocked_without_value():
    rec = recommend_micronutrient(SoilContext(), Nutrient.FE)
    assert rec.status == RecommendationStatus.BLOCKED
    assert "الحديد" in rec.rate_ar
    assert rec.source_ar == "—"


def test_zinc_blocked_without_value():
    rec = recommend_micronutrient(SoilContext(), Nutrient.ZN)
    assert rec.status == RecommendationStatus.BLOCKED
    assert "الزنك" in rec.rate_ar


def test_iron_with_value_is_advisory_foliar_chelate():
    rec = recommend_micronutrient(SoilContext(fe_ppm=2.0), Nutrient.FE)
    assert rec.status == RecommendationStatus.ADVISORY
    assert "Fe-EDDHA" in rec.source_ar  # مصدر مخلّبي للحديد
    assert "ورقي" in rec.placement_ar  # تطبيق ورقي
    assert "2.0" in rec.rate_ar


def test_zinc_with_value_uses_zinc_source():
    rec = recommend_micronutrient(SoilContext(zn_ppm=1.0), Nutrient.ZN)
    assert rec.status == RecommendationStatus.ADVISORY
    assert "كبريتات الزنك" in rec.source_ar
    assert "الزنك" in rec.rate_ar


def test_micronutrient_selects_correct_value_field():
    # FE يقرأ fe_ppm فقط: zn_ppm مُعطًى لكن fe_ppm None ⇒ يبقى محجوباً.
    rec = recommend_micronutrient(SoilContext(zn_ppm=1.0), Nutrient.FE)
    assert rec.status == RecommendationStatus.BLOCKED


# ─── الخطة الكاملة ────────────────────────────────────────────────────────


def test_full_plan_default_covers_npFeZn():
    plan = full_4r_plan(SoilContext())
    assert [p["nutrient"] for p in plan] == [
        Nutrient.N.value,
        Nutrient.P.value,
        Nutrient.FE.value,
        Nutrient.ZN.value,
    ]
    # كلّ عنصر dict مكتمل (مرّ عبر to_dict).
    for p in plan:
        assert set(p) == {
            "nutrient",
            "status",
            "source_ar",
            "rate_ar",
            "timing_ar",
            "placement_ar",
            "warnings_ar",
        }


def test_full_plan_blocks_p_fe_zn_for_unanalyzed_soil():
    # تربة بلا تحاليل ⇒ P/Fe/Zn محجوبة، N إرشاديّ.
    plan = {p["nutrient"]: p["status"] for p in full_4r_plan(SoilContext(caco3_pct=25.0))}
    assert plan["nitrogen"] == RecommendationStatus.ADVISORY.value
    assert plan["phosphorus"] == RecommendationStatus.BLOCKED.value
    assert plan["iron"] == RecommendationStatus.BLOCKED.value
    assert plan["zinc"] == RecommendationStatus.BLOCKED.value


def test_full_plan_custom_nutrient_subset():
    plan = full_4r_plan(SoilContext(), ["nitrogen"])
    assert len(plan) == 1
    assert plan[0]["nutrient"] == Nutrient.N.value


def test_full_plan_unknown_nutrient_raises():
    with pytest.raises(ValueError):
        full_4r_plan(SoilContext(), ["unobtanium"])


# ─── to_dict ──────────────────────────────────────────────────────────────


def test_to_dict_round_trips_fields():
    rec = FourRRecommendation(
        nutrient=Nutrient.K,
        status=RecommendationStatus.OK,
        source_ar="مصدر",
        rate_ar="معدّل",
        timing_ar="وقت",
        placement_ar="مكان",
        warnings_ar=["تحذير"],
    )
    d = rec.to_dict()
    assert d["nutrient"] == "potassium"
    assert d["status"] == "ok"
    assert d["warnings_ar"] == ["تحذير"]


def test_recommendation_default_warnings_is_empty_list():
    rec = FourRRecommendation(
        nutrient=Nutrient.N,
        status=RecommendationStatus.ADVISORY,
        source_ar="s",
        rate_ar="r",
        timing_ar="t",
        placement_ar="p",
    )
    assert rec.warnings_ar == []
