"""اختبار منحنى امتصاص العنصر عبر المراحل (Nutrient Uptake Curve) — نقيّ حتميّ.

يثبت: (أ) Σ نِسَب الامتصاص = 1.0؛ (ب) توزيع الكمّيّة على الهدف الكلّيّ؛ (ج) التراكم
"حتى الآن" باسم مرحلة (شامل)؛ (د) التراكم بتقدّم [0,1] (استيفاء عبر أطوال المراحل)؛
(هـ) مرحلة مجهولة ⇒ تحذير وتراكم=0؛ (و) هدف صفر/سالب ⇒ كمّيّات صفريّة بلا تلفيق؛
(ز) موسوم calibrated=False؛ (ح) ترتيب المراحل من المصدر الموحّد _STAGE_FRACTIONS.
نواة بلا شبكة/قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.nutrient_4r import nutrient_uptake  # noqa: E402


def test_uptake_fractions_sum_to_one():
    res = nutrient_uptake("wheat", None, 100.0)
    total = sum(s["stage_fraction"] for s in res["stages"])
    assert total == pytest.approx(1.0)
    assert res["stages"][-1]["cumulative_fraction"] == pytest.approx(1.0)


def test_amounts_distribute_target():
    res = nutrient_uptake("tomato", None, 200.0)  # بطاقة بلا منحنى ⇒ المنحنى العامّ
    total_kg = sum(s["uptake_kg_ha"] for s in res["stages"])
    assert total_kg == pytest.approx(200.0)
    # mid = 0.40 من 200 = 80.
    mid = next(s for s in res["stages"] if s["stage"] == "mid")
    assert mid["uptake_kg_ha"] == pytest.approx(80.0)


def test_to_date_by_stage_name_is_inclusive():
    # كانت "wheat" — وبطاقة القمح تحمل منحناها الخاصّ الآن (0.05+0.35=0.40)؛ العامّ لمحصول بلا منحنى.
    res = nutrient_uptake("tomato", "development", 100.0)
    # initial 0.10 + development 0.35 = 0.45.
    assert res["matched_stage"] == "development"
    assert res["cumulative_fraction_to_date"] == pytest.approx(0.45)
    assert res["uptake_to_date_kg_ha"] == pytest.approx(45.0)


def test_to_date_full_season_by_late_stage():
    res = nutrient_uptake("wheat", "late", 100.0)
    assert res["cumulative_fraction_to_date"] == pytest.approx(1.0)
    assert res["uptake_to_date_kg_ha"] == pytest.approx(100.0)


def test_to_date_by_progress_interpolates():
    # المنحنى العامّ (محصول بلا منحنى بطاقة): p=0.20 = نهاية initial تماماً ⇒ تراكم = 0.10.
    res = nutrient_uptake("tomato", 0.20, 100.0)
    assert res["cumulative_fraction_to_date"] == pytest.approx(0.10)
    # p=0.35 = منتصف development (حدوده [0.20,0.50]، نصفه) ⇒ 0.10 + 0.5×0.35 = 0.275.
    res2 = nutrient_uptake("tomato", 0.35, 100.0)
    assert res2["cumulative_fraction_to_date"] == pytest.approx(0.275)
    assert res2["matched_stage"] == "development"


def test_progress_zero_and_one_bounds():
    assert nutrient_uptake("wheat", 0.0, 100.0)["cumulative_fraction_to_date"] == pytest.approx(0.0)
    assert nutrient_uptake("wheat", 1.0, 100.0)["cumulative_fraction_to_date"] == pytest.approx(1.0)
    # خارج النطاق يُقصّ.
    assert nutrient_uptake("wheat", 5.0, 100.0)["cumulative_fraction_to_date"] == pytest.approx(1.0)


def test_unknown_stage_warns_and_zero_to_date():
    res = nutrient_uptake("wheat", "nonexistent", 100.0)
    assert res["matched_stage"] is None
    assert res["cumulative_fraction_to_date"] == 0.0
    assert any("غير معروفة" in w for w in res["warnings_ar"])


def test_zero_and_negative_target_no_fabrication():
    zero = nutrient_uptake("wheat", "mid", 0.0)
    assert all(s["uptake_kg_ha"] == 0.0 for s in zero["stages"])
    assert zero["uptake_to_date_kg_ha"] == 0.0
    neg = nutrient_uptake("wheat", "mid", -50.0)
    assert neg["target_uptake_kg_ha"] == 0.0
    assert any("سالب" in w for w in neg["warnings_ar"])


def test_flagged_uncalibrated():
    res = nutrient_uptake("wheat", None, 100.0)
    assert res["calibrated"] is False
    assert any("غير معايَر" in w for w in res["warnings_ar"])


def test_stage_order_matches_canonical_source():
    from api.season_simulation import _STAGE_FRACTIONS

    res = nutrient_uptake("wheat", None, 100.0)
    assert [s["stage"] for s in res["stages"]] == [name for name, _ in _STAGE_FRACTIONS]


def test_none_progress_gives_full_curve_no_to_date():
    res = nutrient_uptake(None, None, 100.0)
    assert res["crop"] is None
    assert res["matched_stage"] is None
    assert res["cumulative_fraction_to_date"] == 0.0
    assert len(res["stages"]) == 4


# ── منحنى البطاقة أوّلاً (المراجعة R14-F2): القمح/الذرة يحملان منحنى N-P-K مرحليّاً ──────


def _card_fracs(crop_id: str, element: str) -> list[float]:
    from core.crop_cards.loader import stage_nutrient_demand

    return [st[f"{element}_fraction"] for st in stage_nutrient_demand(crop_id)]


@pytest.mark.parametrize("crop", ["wheat", "maize", "sorghum", "قمح صلب", "ذرة صفراء"])
@pytest.mark.parametrize("element", ["n", "p", "k"])
def test_card_curve_is_read_first(crop, element):
    from core.season_phenology import resolve_crop_id

    res = nutrient_uptake(crop, None, 100.0, nutrient=element)
    assert res["source"] == "crop_card"
    assert res["nutrient"] == element
    assert res["calibrated"] is False  # تقريب أدبيّ، لا معايرة محلّيّة
    expected = _card_fracs(resolve_crop_id(crop), element)
    assert [s["stage_fraction"] for s in res["stages"]] == pytest.approx(expected)


def test_gap_named_values_wheat_and_maize_nitrogen():
    # العامّ 0.10/0.35/0.40/0.15 ⇒ البطاقة: قمح 0.05/0.35/0.40/0.20 · ذرة 0.05/0.40/0.45/0.10.
    wheat = [s["stage_fraction"] for s in nutrient_uptake("wheat", None, 1.0)["stages"]]
    maize = [s["stage_fraction"] for s in nutrient_uptake("maize", None, 1.0)["stages"]]
    assert wheat == pytest.approx([0.05, 0.35, 0.40, 0.20])
    assert maize == pytest.approx([0.05, 0.40, 0.45, 0.10])


def test_card_curve_uses_the_card_stage_windows_for_progress():
    # القمح: نوافذ البطاقة [0–15, 15–40, 40–90, 90–120] من 120 يوماً ⇒ نهاية initial عند 0.125.
    res = nutrient_uptake("wheat", 15 / 120, 100.0)
    assert res["cumulative_fraction_to_date"] == pytest.approx(0.05)
    assert res["matched_stage"] == "initial"
    assert nutrient_uptake("wheat", "development", 100.0)["cumulative_fraction_to_date"] == (
        pytest.approx(0.40)
    )


@pytest.mark.parametrize("crop", [None, "dragonfruit", "tomato", "خضروات"])
def test_no_card_curve_falls_back_to_generic_and_says_so(crop):
    from api.nutrient_4r import _UPTAKE_FRACTIONS

    res = nutrient_uptake(crop, None, 100.0)
    assert res["source"] == "generic"
    assert res["calibrated"] is False
    assert [s["stage_fraction"] for s in res["stages"]] == [
        _UPTAKE_FRACTIONS[s["stage"]] for s in res["stages"]
    ]


def test_unsupported_nutrient_is_refused():
    with pytest.raises(ValueError):
        nutrient_uptake("wheat", None, 100.0, nutrient="fe")


def test_crop_twin_nutrient_state_follows_the_card_curve():
    from api.crop_twin import TwinDay, crop_twin_state

    days = [TwinDay(t_min_c=10.0, t_max_c=30.0, et0_mm=5.0, kc=1.0)] * 3
    # The twin no longer fabricates zero growth without GDD, so the series is supplied.
    gdd = [20.0] * len(days)
    out = crop_twin_state(
        "wheat",
        days,
        taw_mm=150.0,
        raw_fraction=0.5,
        target_uptake_kg_ha=120.0,
        gdd_daily_override=gdd,
    )
    assert out["nutrient"]["curve_source"] == "crop_card"
    assert out["nutrient"]["nutrient"] == "n"
    progress = out["phenology"]["progress"]
    assert progress > 0
    assert out["nutrient"]["cumulative_fraction_to_date"] == pytest.approx(
        nutrient_uptake("wheat", progress, 120.0)["cumulative_fraction_to_date"]
    )
    generic = crop_twin_state(
        "dragonfruit", days, taw_mm=150.0, raw_fraction=0.5, target_uptake_kg_ha=120.0
    )
    assert generic["nutrient"]["curve_source"] == "generic"
