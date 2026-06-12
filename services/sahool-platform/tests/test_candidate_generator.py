"""اختبارات مولّد البدائل (offline) — تقييم متعدّد الأهداف، شفّاف، يحترم الوكالة.

يتحقّق من: التقييم الحتميّ حسب الهدف، أنّ كلّ الخيارات تبقى مرئيّة (حتى غير
المناسب)، إبراز الأعلى، تفكيك الدرجة الشفّاف، ومعاملة الصفات المجهولة محايدةً.
"""

from core.engines.candidate_generator import (
    CropCandidate,
    FarmerGoal,
    generate_candidates,
    score_candidate,
)

# ─── أمثلة موثّقة ─────────────────────────────────────────────────────────


def _sorghum():  # أصمد للجفاف، حاجة ماء منخفضة، أساسي
    return CropCandidate(
        crop_id="sorghum",
        name_ar="الذرة الرفيعة",
        is_suited=True,
        water_need_level="low",
        upfront_cost_level="low",
        profit_potential_level="mid",
        is_staple=True,
        drought_score=0.8,
    )


def _grape():  # ربح عالٍ، حاجة ماء عالية، تكلفة عالية، غير أساسي
    return CropCandidate(
        crop_id="grape",
        name_ar="العنب",
        is_suited=True,
        water_need_level="high",
        upfront_cost_level="high",
        profit_potential_level="high",
        is_staple=False,
        drought_score=0.4,
    )


# ─── التقييم حسب الهدف ────────────────────────────────────────────────────


def test_min_water_goal_prefers_low_water_crop():
    out = generate_candidates([_grape(), _sorghum()], FarmerGoal.MIN_WATER)
    assert out["recommended"]["crop_id"] == "sorghum"  # حاجة ماء أقلّ
    assert out["goal"] == "min_water"


def test_max_profit_goal_prefers_high_profit_crop():
    out = generate_candidates([_sorghum(), _grape()], FarmerGoal.MAX_PROFIT)
    assert out["recommended"]["crop_id"] == "grape"  # ربح أعلى


def test_drought_goal_prefers_resilient_crop():
    out = generate_candidates([_grape(), _sorghum()], FarmerGoal.DROUGHT_RESILIENCE)
    assert out["recommended"]["crop_id"] == "sorghum"  # درجة تحمّل أعلى


# ─── الوكالة: لا حذف ─────────────────────────────────────────────────────


def test_all_options_visible_including_unsuited():
    # خيار غير مناسب يبقى معروضاً (مُرتَّب أدنى) — استقلاليّة المزارع
    unsuited = CropCandidate("banana", "الموز", is_suited=False, drought_score=0.1)
    out = generate_candidates([_sorghum(), unsuited], FarmerGoal.FOOD_SECURITY)
    ids = [c["crop_id"] for c in out["candidates"]]
    assert "banana" in ids  # لم يُحذف
    assert out["all_options_visible"] is True
    # غير المناسب أدنى ترتيباً
    banana = next(c for c in out["candidates"] if c["crop_id"] == "banana")
    assert banana["rank"] == len(out["candidates"])
    assert any("غير مناسب" in f for f in banana["flags_ar"])


def test_display_only_and_agency_note_present():
    out = generate_candidates([_sorghum()], FarmerGoal.MAX_PROFIT)
    assert out["display_only"] is True  # لا تفرض قراراً
    assert out["agency_note_ar"]
    assert out["honesty_note_ar"]


# ─── الشفافيّة + الصفات المجهولة ─────────────────────────────────────────


def test_score_breakdown_is_transparent():
    s = score_candidate(_sorghum(), FarmerGoal.MIN_WATER)
    # كلّ مكوّن يُظهر قيمته ووزنه وإسهامه ومصدره
    for comp in s["breakdown"].values():
        assert {"value", "weight", "contribution", "source_ar"} <= comp.keys()
    # مجموع الإسهامات = الدرجة (ضمن تقريب)
    total = sum(c["contribution"] for c in s["breakdown"].values())
    assert abs(total - s["score"]) < 1e-6


def test_unknown_attributes_are_neutral_and_flagged():
    c = CropCandidate("mystery", "مجهول", is_suited=True)  # drought/profit مجهولان
    s = score_candidate(c, FarmerGoal.MAX_PROFIT)
    assert s["breakdown"]["drought"]["value"] == 0.5  # محايد
    assert s["breakdown"]["profit"]["value"] == 0.5  # محايد (unknown)
    assert any("مجهول" in f for f in s["flags_ar"])


def test_highlighted_marks_top_n():
    cands = [
        _sorghum(),
        _grape(),
        CropCandidate("millet", "الدخن", is_suited=True, drought_score=0.7),
    ]
    out = generate_candidates(cands, FarmerGoal.DROUGHT_RESILIENCE, top_n=2)
    highlighted = [c for c in out["candidates"] if c["highlighted"]]
    assert len(highlighted) == 2  # الأعلى اثنان فقط مُبرَزان
    assert all(c["rank"] <= 2 for c in highlighted)
