"""اختبارات ذكاء التناوب الزراعيّ (core.crop_rotation_intelligence) — نقيّ، حتميّ.

يغطّي: تناوب متنوّع شامل بقوليّات ⇒ اتّجاه موجب + درجة عالية + نسبة بقوليّات > 0؛
زراعة أحاديّة صرفة ⇒ اتّجاه سالب + خطر تكرار عالٍ + أطول جريّة = n؛ سجلّ فارغ ⇒
محايد بلا انهيار وseasons_analyzed=0؛ بقاء كلّ المؤشّرات ضمن حدودها الموثّقة؛
حساب نِسَب الغطاء/التحميل البينيّ على حالة مُصمَّمة؛ رصد البقوليّ من التحميل البينيّ.
"""

from __future__ import annotations

import pytest
from core.crop_rotation_intelligence import (
    RotationAssessment,
    SeasonCrop,
    assess_rotation,
)

pytestmark = pytest.mark.unit


def _diverse_rotation() -> list[SeasonCrop]:
    """تناوب متنوّع شامل بقوليّات وغطاء وتحميل بينيّ (تغذية راجعة موجبة)."""
    return [
        SeasonCrop(season_id="s1", crop_id="wheat", crop_family="poaceae"),
        SeasonCrop(season_id="s2", crop_id="faba_bean", crop_family="fabaceae", is_legume=True),
        SeasonCrop(season_id="s3", crop_id="tomato", crop_family="solanaceae"),
        SeasonCrop(
            season_id="s4",
            crop_id="clover",
            crop_family="fabaceae",
            is_legume=True,
            is_cover_crop=True,
        ),
    ]


def _monoculture(n: int = 5) -> list[SeasonCrop]:
    """زراعة أحاديّة صرفة: نفس المحصول/العائلة كلّ موسم."""
    return [SeasonCrop(season_id=f"s{i}", crop_id="maize", crop_family="poaceae") for i in range(n)]


def _assert_bounds(a: RotationAssessment) -> None:
    """كلّ المؤشّرات [0,1] والدرجة [0,100] والجريّة غير سالبة."""
    for v in (
        a.rotation_diversity_index,
        a.legume_ratio,
        a.cover_crop_ratio,
        a.intercropping_ratio,
        a.host_repeat_risk,
    ):
        assert 0.0 <= v <= 1.0
    assert 0.0 <= a.rotation_score <= 100.0
    assert a.max_consecutive_same >= 0
    assert a.direction in ("positive", "negative", "neutral")


def test_diverse_rotation_positive_direction():
    a = assess_rotation(_diverse_rotation())
    assert a.direction == "positive"
    assert a.rotation_score >= 60.0
    assert a.legume_ratio > 0.0
    assert a.seasons_analyzed == 4
    _assert_bounds(a)


def test_diverse_rotation_diversity_index_full():
    a = assess_rotation(_diverse_rotation())
    # ثلاث عائلات مميّزة (poaceae, fabaceae, solanaceae) عبر أربعة مواسم ⇒ 3/4.
    assert a.rotation_diversity_index == pytest.approx(0.75)
    assert a.max_consecutive_same == 1
    assert a.host_repeat_risk == pytest.approx(0.0)


def test_monoculture_negative_and_high_repeat():
    n = 5
    a = assess_rotation(_monoculture(n))
    assert a.direction == "negative"
    assert a.max_consecutive_same == n
    assert a.host_repeat_risk == pytest.approx(1.0)  # كلّ المواقع تكرار
    assert a.rotation_diversity_index == pytest.approx(1.0 / n)
    _assert_bounds(a)


def test_empty_history_neutral_no_crash():
    a = assess_rotation([])
    assert a.seasons_analyzed == 0
    assert a.direction == "neutral"
    assert a.rotation_score == 0.0
    assert a.max_consecutive_same == 0
    assert a.evidence_ar  # دليل عربيّ غير فارغ على عدم كفاية البيانات
    _assert_bounds(a)


def test_single_season_no_repeat_risk():
    a = assess_rotation([SeasonCrop(season_id="s1", crop_id="wheat")])
    assert a.seasons_analyzed == 1
    assert a.host_repeat_risk == pytest.approx(0.0)  # لا قسمة على صفر
    assert a.max_consecutive_same == 1
    _assert_bounds(a)


def test_cover_and_intercrop_ratios():
    history = [
        SeasonCrop(season_id="s1", crop_id="wheat", is_cover_crop=True),
        SeasonCrop(
            season_id="s2",
            crop_id="tomato",
            intercropped_with=("basil",),
        ),
        SeasonCrop(season_id="s3", crop_id="potato"),
        SeasonCrop(
            season_id="s4",
            crop_id="onion",
            is_cover_crop=True,
            intercropped_with=("carrot",),
        ),
    ]
    a = assess_rotation(history)
    assert a.cover_crop_ratio == pytest.approx(2 / 4)  # s1, s4
    assert a.intercropping_ratio == pytest.approx(2 / 4)  # s2, s4
    _assert_bounds(a)


def test_legume_detected_from_intercrop():
    # الرئيس غير بقوليّ، لكن التحميل البينيّ يحوي بقوليّاً معروفاً ⇒ يُحتسب الموسم.
    history = [
        SeasonCrop(
            season_id="s1",
            crop_id="maize",
            intercropped_with=("cowpea",),
        ),
        SeasonCrop(season_id="s2", crop_id="wheat"),
    ]
    a = assess_rotation(history)
    assert a.legume_ratio == pytest.approx(1 / 2)
    _assert_bounds(a)


def test_legume_crop_id_without_flag_counts():
    # معرّف بقوليّ معروف بلا رفع علَم is_legume ⇒ يُحتسب بقوليّاً.
    history = [
        SeasonCrop(season_id="s1", crop_id="lentil"),
        SeasonCrop(season_id="s2", crop_id="wheat"),
    ]
    a = assess_rotation(history)
    assert a.legume_ratio == pytest.approx(1 / 2)


def test_alternating_family_not_negative():
    # تناوب A,B,A,B: لا تكرار متتالٍ ⇒ خطر تكرار 0، اتّجاه ليس سالباً.
    history = [
        SeasonCrop(
            season_id=f"s{i}", crop_id="wheat" if i % 2 == 0 else "bean", is_legume=(i % 2 == 1)
        )
        for i in range(4)
    ]
    a = assess_rotation(history)
    assert a.host_repeat_risk == pytest.approx(0.0)
    assert a.max_consecutive_same == 1
    assert a.direction != "negative"
    _assert_bounds(a)


def test_partial_repeat_intermediate_risk():
    # [A,A,B,C]: تكرار واحد متتالٍ ÷ (4−1) = 1/3.
    history = [
        SeasonCrop(season_id="s1", crop_id="wheat", crop_family="poaceae"),
        SeasonCrop(season_id="s2", crop_id="barley", crop_family="poaceae"),
        SeasonCrop(season_id="s3", crop_id="tomato", crop_family="solanaceae"),
        SeasonCrop(season_id="s4", crop_id="bean", crop_family="fabaceae", is_legume=True),
    ]
    a = assess_rotation(history)
    # s1,s2 نفس العائلة poaceae ⇒ تكرار متتالٍ واحد (مُدوَّر إلى 4 منازل).
    assert a.host_repeat_risk == pytest.approx(0.3333, abs=1e-4)
    assert a.max_consecutive_same == 2
    _assert_bounds(a)
