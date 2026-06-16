"""اختبارات محرّك ملاءمة المحاصيل (api.crop_suitability) — دوالّ نقيّة offline.

يتحقّق من `_score_range` عند الحدود (داخل/تحت/فوق الأمثل والمحتمَل)، ومن
`score_crop` عبر ظروف جيّدة مقابل سيّئة (القيد الحاسم للملوحة، الحرارة، المطر
للبعل)، ومن نطاقات الدرجات → التقييم (ممتاز/جيّد/حدّي/غير مناسب)، ومن
`rank_crops` (الترتيب، حجب نقص بيانات التربة، التنبيه عند التقارب).
كلّ القيم مشتقّة من ثوابت الوحدة نفسها (FAO) لا من افتراض.
"""

import pytest
from api.crop_suitability import (
    CROP_TOLERANCES,
    CropTolerance,
    FieldConditions,
    SuitabilityScore,
    _score_range,
    rank_crops,
    score_crop,
)

pytestmark = pytest.mark.unit

# القمح: ph_optimal (6.0,7.5)، ph_tolerable (5.5,8.5)، ec_max 6.0، rain_min 300، temp (10,25)
_WHEAT = next(t for t in CROP_TOLERANCES if t.crop == "wheat")


# ─── _score_range: الحدود ────────────────────────────────────────────────


def test_score_range_within_optimal_is_one():
    assert _score_range(7.0, (6.0, 7.5), (5.5, 8.5)) == 1.0
    # الحدّان الأمثلان شاملان.
    assert _score_range(6.0, (6.0, 7.5), (5.5, 8.5)) == 1.0
    assert _score_range(7.5, (6.0, 7.5), (5.5, 8.5)) == 1.0


def test_score_range_below_tolerable_is_zero():
    assert _score_range(5.0, (6.0, 7.5), (5.5, 8.5)) == 0.0


def test_score_range_above_tolerable_is_zero():
    assert _score_range(9.0, (6.0, 7.5), (5.5, 8.5)) == 0.0


def test_score_range_linear_decay_below_optimal():
    # بين lo_t(5.5) و lo_o(6.0): (5.75-5.5)/(6.0-5.5) = 0.5
    assert _score_range(5.75, (6.0, 7.5), (5.5, 8.5)) == 0.5


def test_score_range_linear_decay_above_optimal():
    # بين hi_o(7.5) و hi_t(8.5): (8.5-8.0)/(8.5-7.5) = 0.5
    assert _score_range(8.0, (6.0, 7.5), (5.5, 8.5)) == 0.5


def test_score_range_at_tolerable_edges_is_zero():
    # عند حافّة المحتمَل تماماً تؤول الدرجة إلى صفر.
    assert _score_range(8.5, (6.0, 7.5), (5.5, 8.5)) == 0.0


# ─── score_crop: ظروف جيّدة مقابل سيّئة ──────────────────────────────────


def test_excellent_conditions_score_one_and_rate_mumtaz():
    # ph أمثل، ملوحة ≤ نصف الأقصى (ec_s=1)، مرويّ (rain=1)، حرارة داخل المدى.
    s = score_crop(FieldConditions(ph=6.8, ec_dsm=2.0, temp_mean_c=20), _WHEAT)
    assert isinstance(s, SuitabilityScore)
    assert s.score == 1.0
    assert s.rating_ar == "ممتاز"
    assert s.crop == "wheat"


def test_salinity_above_tolerance_hard_fails():
    # الملوحة (10) تتجاوز ec_max(6.0) ⇒ ec_s=0 ⇒ قيد حاسم يسقف الدرجة عند 0.35.
    s = score_crop(FieldConditions(ph=6.8, ec_dsm=10.0, temp_mean_c=20), _WHEAT)
    assert s.score == pytest.approx(0.35)
    assert s.rating_ar == "غير مناسب"
    assert any("الملوحة" in r for r in s.reasons_ar)


def test_salinity_at_half_max_keeps_full_ec_score():
    # عند نصف الأقصى بالضبط (3.0) تبقى درجة الملوحة 1.0 ⇒ الدرجة الكلّيّة ممتازة.
    s = score_crop(FieldConditions(ph=6.8, ec_dsm=3.0, temp_mean_c=20), _WHEAT)
    assert s.score == 1.0


def test_temperature_outside_range_reduces_score():
    # حرارة خارج (10,25) ⇒ temp_s=0.3: 1*0.25 + 1*0.35 + 1*0.20 + 0.3*0.20 = 0.86
    s = score_crop(FieldConditions(ph=6.8, ec_dsm=2.0, temp_mean_c=40), _WHEAT)
    assert s.score == pytest.approx(0.86)
    assert s.rating_ar == "ممتاز"


def test_rainfed_low_rain_penalizes_and_warns():
    # غير مرويّ بمطر 100 دون rain_min 300 ⇒ rain_s=100/300؛ تحذير عند rain_s<0.7.
    s = score_crop(
        FieldConditions(ph=6.8, ec_dsm=2.0, temp_mean_c=20, season_rain_mm=100, irrigated=False),
        _WHEAT,
    )
    assert s.score == pytest.approx(1 * 0.25 + 1 * 0.35 + (100 / 300) * 0.20 + 1 * 0.20)
    assert any("المطر" in r for r in s.reasons_ar)


def test_ph_outside_tolerance_hard_fails():
    # ph 9.0 خارج المحتمَل (5.5,8.5) ⇒ ph_s=0 ⇒ قيد حاسم يسقف عند 0.35.
    s = score_crop(FieldConditions(ph=9.0, ec_dsm=2.0, temp_mean_c=20), _WHEAT)
    assert s.score <= 0.35
    assert s.rating_ar == "غير مناسب"
    assert any("الحموضة" in r and "خارج" in r for r in s.reasons_ar)


def test_to_dict_rounds_score_and_keeps_fields():
    s = score_crop(FieldConditions(ph=6.8, ec_dsm=2.0, temp_mean_c=20), _WHEAT)
    d = s.to_dict()
    assert d["crop"] == "wheat"
    assert d["name_ar"] == "قمح"
    assert d["score"] == 1.0
    assert d["rating_ar"] == "ممتاز"
    assert isinstance(d["reasons_ar"], list) and d["reasons_ar"]


# ─── rank_crops: الترتيب، الحجب، التنبيه ─────────────────────────────────


def test_rank_crops_orders_descending_by_score():
    res = rank_crops(FieldConditions(ph=6.8, ec_dsm=2.0, temp_mean_c=20))
    scores = [c["score"] for c in res["ranked"]]
    assert scores == sorted(scores, reverse=True)
    assert "disclaimer_ar" in res


def test_rank_crops_subset_filters_to_requested():
    res = rank_crops(FieldConditions(ph=6.8, ec_dsm=2.0), crops=["wheat"])
    assert [c["crop"] for c in res["ranked"]] == ["wheat"]
    assert res["ranked"][0]["rating_ar"] == "ممتاز"


def test_rank_crops_unknown_crop_filter_raises():
    with pytest.raises(ValueError):
        rank_crops(FieldConditions(ph=6.8, ec_dsm=2.0), crops=["banana"])


def test_rank_crops_close_top_two_emits_note():
    # القمح والشعير متطابقان عمليّاً في ظروف معتدلة ⇒ فرق <0.1 ⇒ تنبيه.
    res = rank_crops(FieldConditions(ph=6.8, ec_dsm=1.0, temp_mean_c=20), crops=["wheat", "barley"])
    assert res["note_ar"]
    assert "مهندس" in res["note_ar"]


def test_field_conditions_defaults():
    fc = FieldConditions(ph=6.8, ec_dsm=2.0)
    assert fc.season_rain_mm is None
    assert fc.temp_mean_c is None
    assert fc.irrigated is True


def test_crop_tolerance_table_is_populated():
    assert CROP_TOLERANCES
    assert all(isinstance(t, CropTolerance) for t in CROP_TOLERANCES)
    assert _WHEAT.ec_max_dsm == 6.0
