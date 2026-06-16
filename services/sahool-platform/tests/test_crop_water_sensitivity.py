"""اختبارات حساسيّة المراحل للإجهاد المائي (api.crop_water_sensitivity) — نقيّة offline.

تتحقّق من المنطق الصرف بلا قاعدة/شبكة: حلّ أسماء المحاصيل (إنجليزي/عربي/مرادفات)،
قائمة المدعوم، البحث عن المراحل وحساسيّتها، نافذة الحرج (critical window)، تقييم خطر
الإجهاد عند عتبات النضوب، والتوصية المتكاملة. كلّ القيم مشتقّة من ثوابت الوحدة نفسها.
"""

import pytest
from api.crop_water_sensitivity import (
    _CROPS,
    StageSensitivity,
    WaterSensitivity,
    _resolve,
    assess_stress_risk,
    get_stage_sensitivity,
    integrated_irrigation_advice,
    supported_crops,
    water_calendar,
)

pytestmark = pytest.mark.unit


# ─── _resolve: إنجليزي/حالة الأحرف/مرادفات عربيّة/مجهول ───────────────────────


def test_resolve_known_english_key():
    assert _resolve("wheat") == "wheat"


def test_resolve_is_case_insensitive_and_trims():
    assert _resolve("  WHEAT  ") == "wheat"


def test_resolve_arabic_alias_to_english_key():
    assert _resolve("قمح") == "wheat"
    assert _resolve("دخن") == "millet"
    assert _resolve("شعير") == "barley"


def test_resolve_ambiguous_arabic_dhura_maps_to_sorghum():
    # «ذرة» مفرداً مرادف للذرة الرفيعة (sorghum) لا الشاميّة في سجلّ المرادفات.
    assert _resolve("ذرة") == "sorghum"
    assert _resolve("ذرة شاميّة") == "maize"


def test_resolve_unknown_crop_returns_none():
    assert _resolve("tomato") is None


# ─── supported_crops: الشكل والمحتوى ─────────────────────────────────────────


def test_supported_crops_lists_all_five_in_order():
    crops = supported_crops()
    assert [c["crop"] for c in crops] == ["wheat", "maize", "sorghum", "millet", "barley"]


def test_supported_crops_entries_expose_display_fields():
    crops = supported_crops()
    first = crops[0]
    assert set(first.keys()) == {"crop", "name_ar", "drought_tolerance_ar", "season_ar"}
    assert first["crop"] == "wheat"
    assert first["name_ar"] == "القمح"


# ─── get_stage_sensitivity: حساسيّة المراحل ونافذة الحرج ──────────────────────


def test_stage_sensitivity_critical_stage_fields():
    ss = get_stage_sensitivity("wheat", "stem_elongation")
    assert isinstance(ss, StageSensitivity)
    assert ss.sensitivity is WaterSensitivity.CRITICAL
    assert ss.water_share_pct == 25
    assert ss.is_critical_window is True


def test_stage_sensitivity_high_is_critical_window():
    # HIGH أو CRITICAL تُعتبر ضمن نافذة الحرج.
    ss = get_stage_sensitivity("wheat", "grain_filling")
    assert ss.sensitivity is WaterSensitivity.HIGH
    assert ss.is_critical_window is True


def test_stage_sensitivity_low_is_not_critical_window():
    ss = get_stage_sensitivity("wheat", "maturity")
    assert ss.sensitivity is WaterSensitivity.LOW
    assert ss.is_critical_window is False


def test_stage_sensitivity_moderate_is_not_critical_window():
    ss = get_stage_sensitivity("wheat", "tillering")
    assert ss.sensitivity is WaterSensitivity.MODERATE
    assert ss.is_critical_window is False


def test_stage_sensitivity_resolves_arabic_alias():
    ss = get_stage_sensitivity("قمح", "flowering")
    assert ss is not None
    assert ss.sensitivity is WaterSensitivity.CRITICAL


def test_stage_sensitivity_unknown_stage_returns_none():
    assert get_stage_sensitivity("wheat", "no_such_stage") is None


def test_stage_sensitivity_unknown_crop_returns_none():
    assert get_stage_sensitivity("tomato", "maturity") is None


def test_stage_sensitivity_to_dict_uses_enum_value():
    d = get_stage_sensitivity("maize", "tasseling").to_dict()
    assert d["sensitivity"] == "critical"  # القيمة النصّيّة لا العضو
    assert d["stage_key"] == "tasseling"
    assert d["is_critical_window"] is True
    assert d["water_share_pct"] == 30


# ─── سلامة سجلّ المحاصيل: حصص الماء تجمع 100% لكلّ محصول ───────────────────────


def test_each_crop_water_shares_sum_to_100():
    for crop, data in _CROPS.items():
        total = sum(stage[3] for stage in data["stages"])
        assert total == 100, f"{crop} shares sum to {total}"


# ─── water_calendar ──────────────────────────────────────────────────────────


def test_water_calendar_supported_crop_full_shape():
    wc = water_calendar("maize")
    assert wc["supported"] is True
    assert wc["crop"] == "maize"
    assert wc["crop_ar"] == "الذرة الشاميّة"
    # كلّ مراحل المحصول مُسلسَلة كـdicts.
    assert len(wc["stages"]) == len(_CROPS["maize"]["stages"])
    assert all("sensitivity" in s for s in wc["stages"])


def test_water_calendar_unknown_crop_not_supported():
    wc = water_calendar("tomato")
    assert wc["supported"] is False
    assert "tomato" in wc["message_ar"]


# ─── assess_stress_risk: عتبات النضوب ونافذة الحرج ────────────────────────────


def test_stress_severe_at_80pct():
    r = assess_stress_risk("wheat", "flowering", 85)
    assert r["supported"] is True
    assert r["stress_level"] == "severe"
    assert r["stress_level_ar"] == "إجهاد شديد"


def test_stress_moderate_between_70_and_80():
    r = assess_stress_risk("wheat", "flowering", 72)
    assert r["stress_level"] == "moderate"


def test_stress_ok_below_70():
    r = assess_stress_risk("wheat", "flowering", 50)
    assert r["stress_level"] == "ok"


def test_stress_boundary_exactly_80_is_severe():
    assert assess_stress_risk("wheat", "flowering", 80)["stress_level"] == "severe"


def test_stress_boundary_exactly_70_is_moderate():
    assert assess_stress_risk("wheat", "flowering", 70)["stress_level"] == "moderate"


def test_urgent_irrigation_when_critical_window_and_depletion_at_least_60():
    # نافذة حرجة (flowering=CRITICAL) + نضوب ≥60 ⇒ ريّ عاجل.
    r = assess_stress_risk("wheat", "flowering", 65)
    assert r["is_critical_window"] is True
    assert r["urgent_irrigation"] is True


def test_no_urgent_irrigation_when_critical_but_depletion_below_60():
    r = assess_stress_risk("wheat", "flowering", 55)
    assert r["is_critical_window"] is True
    assert r["urgent_irrigation"] is False


def test_no_urgent_irrigation_outside_critical_window():
    # النضج (maturity) منخفض الحساسيّة ⇒ ليس نافذة حرجة مهما اشتدّ النضوب.
    r = assess_stress_risk("wheat", "maturity", 90)
    assert r["is_critical_window"] is False
    assert r["urgent_irrigation"] is False


def test_stress_unsupported_crop():
    r = assess_stress_risk("tomato", "flowering", 90)
    assert r["supported"] is False


# ─── integrated_irrigation_advice ────────────────────────────────────────────


def test_integrated_advice_with_irrigation_amount_marks_crop_model():
    out = integrated_irrigation_advice("wheat", "flowering", 85, net_irrigation_mm=40)
    assert out["supported"] is True
    assert out["evidence_type"] == "crop_model"
    assert out["net_irrigation_mm"] == 40.0
    assert "integrated_advice_ar" in out


def test_integrated_advice_unsupported_crop_passes_through():
    out = integrated_irrigation_advice("tomato", "flowering", 85, net_irrigation_mm=40)
    assert out["supported"] is False
    assert "evidence_type" not in out


def test_integrated_advice_without_amount_omits_model_fields():
    out = integrated_irrigation_advice("wheat", "flowering", 85)
    assert out["supported"] is True
    assert "net_irrigation_mm" not in out
    assert "evidence_type" not in out
