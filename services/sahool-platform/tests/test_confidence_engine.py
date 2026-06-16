"""اختبارات محرّك الثقة المكاني/الزماني (api.confidence_engine) — نقيّة offline.

تتحقّق من القواعد الرياضيّة الصرفة (لا AI/ML): تصنيف مستوى الثقة عند حدود النطاقات،
درجات السحب/الحداثة الزمنيّة/التغطية/المصدر، والمتوسّط الهندسي الموزون المركّب
ودالّة الواجهة المُبسَّطة لـNDVI. القيم مشتقّة من معادلات الوحدة نفسها (بلا حقن وقت حيّ).
"""

import math
from datetime import UTC, datetime, timedelta

import pytest
from api.confidence_engine import (
    CloudConfidence,
    ConfidenceLevel,
    CoverageConfidence,
    IndicatorConfidence,
    SourceConfidence,
    TemporalConfidence,
    compute_ndvi_confidence,
    level_from_score,
)

pytestmark = pytest.mark.unit


# ─── level_from_score: حدود النطاقات الأربعة ─────────────────────────────────


def test_level_high_at_and_above_080():
    assert level_from_score(0.80) is ConfidenceLevel.HIGH
    assert level_from_score(1.0) is ConfidenceLevel.HIGH


def test_level_just_below_080_is_medium():
    assert level_from_score(0.799) is ConfidenceLevel.MEDIUM


def test_level_medium_at_055():
    assert level_from_score(0.55) is ConfidenceLevel.MEDIUM


def test_level_just_below_055_is_low():
    assert level_from_score(0.549) is ConfidenceLevel.LOW


def test_level_low_at_035():
    assert level_from_score(0.35) is ConfidenceLevel.LOW


def test_level_just_below_035_is_very_low():
    assert level_from_score(0.349) is ConfidenceLevel.VERY_LOW


def test_level_zero_is_very_low():
    assert level_from_score(0.0) is ConfidenceLevel.VERY_LOW


# ─── CloudConfidence.score ───────────────────────────────────────────────────


def test_cloud_clear_scene_scores_one():
    assert CloudConfidence(cloud_pct=0).score == 1.0


def test_cloud_fully_clouded_scores_zero():
    assert CloudConfidence(cloud_pct=100).score == 0.0


def test_cloud_weighted_contamination():
    # cloud×1.0 + shadow×0.8 + cirrus×0.4، مقسوماً على 100.
    c = CloudConfidence(cloud_pct=50, cloud_shadow_pct=50)
    assert c.score == pytest.approx(0.1)  # 1 - (50 + 40)/100


def test_cloud_cirrus_is_lightly_penalised():
    # السيرس وزنه 0.4 فقط: 100% سيرس ⇒ ثقة 0.6.
    assert CloudConfidence(cloud_pct=0, cirrus_pct=100).score == pytest.approx(0.6)


def test_cloud_score_floored_at_zero():
    # تلوّث > 1.0 لا يهبط تحت الصفر.
    assert CloudConfidence(cloud_pct=100, cloud_shadow_pct=100).score == 0.0


# ─── TemporalConfidence.score ────────────────────────────────────────────────


def test_temporal_same_day_scores_one():
    assert TemporalConfidence(days_since_observation=0).score == 1.0


def test_temporal_negative_days_scores_one():
    assert TemporalConfidence(days_since_observation=-3).score == 1.0


def test_temporal_within_revisit_uses_095_decay():
    assert TemporalConfidence(days_since_observation=1).score == pytest.approx(0.95)
    assert TemporalConfidence(days_since_observation=5).score == pytest.approx(0.95**5)


def test_temporal_beyond_revisit_applies_steeper_decay():
    # يومان فوق الـrevisit (5): 0.95^5 × 0.85^(10-5).
    expected = (0.95**5) * (0.85**5)
    assert TemporalConfidence(days_since_observation=10).score == pytest.approx(expected)


def test_temporal_floored_at_010():
    assert TemporalConfidence(days_since_observation=365).score == 0.1


# ─── CoverageConfidence.score ────────────────────────────────────────────────


def test_coverage_full_scores_one():
    assert CoverageConfidence(pixels_observed=100, pixels_expected=100).score == 1.0


def test_coverage_continuous_at_half():
    # الانحناء التربيعي تحت 0.5 يلتقي 0.5 عند النسبة 0.5 بالضبط (متّصل).
    assert CoverageConfidence(pixels_observed=50, pixels_expected=100).score == pytest.approx(0.5)


def test_coverage_quadratic_penalty_below_half():
    # ratio=0.25 ⇒ 2×0.25² = 0.125.
    assert CoverageConfidence(pixels_observed=25, pixels_expected=100).score == pytest.approx(0.125)


def test_coverage_over_full_clamped_to_one():
    assert CoverageConfidence(pixels_observed=200, pixels_expected=100).score == 1.0


def test_coverage_zero_expected_scores_zero():
    assert CoverageConfidence(pixels_observed=10, pixels_expected=0).score == 0.0


# ─── SourceConfidence.score ──────────────────────────────────────────────────


def test_source_single_no_groundtruth_is_base_half():
    assert SourceConfidence(source_count=1).score == pytest.approx(0.5)


def test_source_ground_truth_adds_020():
    assert SourceConfidence(source_count=1, has_ground_truth=True).score == pytest.approx(0.7)


def test_source_multiple_sensors_increase_score():
    # 0.5 + (4-1)×0.15 = 0.95.
    assert SourceConfidence(source_count=4).score == pytest.approx(0.95)


def test_source_score_clamped_to_one():
    assert SourceConfidence(source_count=5, has_ground_truth=True).score == 1.0


# ─── IndicatorConfidence: التجميع المركّب (متوسّط هندسي موزون) ─────────────────


def test_composite_all_perfect_scores_one_and_high():
    ic = IndicatorConfidence(
        indicator_name="NDVI",
        measurement_value=0.7,
        cloud=CloudConfidence(cloud_pct=0),
        temporal=TemporalConfidence(days_since_observation=0),
        coverage=CoverageConfidence(pixels_observed=100, pixels_expected=100),
        source=SourceConfidence(source_count=4, has_ground_truth=True),
    )
    assert ic.composite_score == 1.0
    assert ic.level is ConfidenceLevel.HIGH
    assert ic.reasons_ar == []
    assert ic.recommendation_ar == "البيانات موثوقة — يمكن الاعتماد عليها."


def test_composite_matches_weighted_geometric_mean():
    cloud = CloudConfidence(cloud_pct=0)
    temporal = TemporalConfidence(days_since_observation=3)
    coverage = CoverageConfidence(pixels_observed=100, pixels_expected=100)
    source = SourceConfidence(source_count=1)
    ic = IndicatorConfidence("NDVI", 0.5, cloud, temporal, coverage, source)
    scores = [
        (cloud.score, 0.30),
        (temporal.score, 0.30),
        (coverage.score, 0.25),
        (source.score, 0.15),
    ]
    log_sum = sum(w * math.log(max(0.01, s)) for s, w in scores)
    assert ic.composite_score == round(math.exp(log_sum), 3)


def test_composite_bad_inputs_are_very_low_with_reasons():
    ic = IndicatorConfidence(
        indicator_name="NDVI",
        measurement_value=0.3,
        cloud=CloudConfidence(cloud_pct=80),
        temporal=TemporalConfidence(days_since_observation=30),
        coverage=CoverageConfidence(pixels_observed=10, pixels_expected=100),
        source=SourceConfidence(source_count=1),
    )
    assert ic.level is ConfidenceLevel.VERY_LOW
    # سحب عالٍ + بيانات قديمة + تغطية ضعيفة. (المصدر score=0.5 ليس <0.5 فلا يُسجَّل.)
    assert any("تغطية سحب" in r for r in ic.reasons_ar)
    assert any("قديمة" in r for r in ic.reasons_ar)
    assert any("البكسلات" in r for r in ic.reasons_ar)
    assert all("مصدر واحد" not in r for r in ic.reasons_ar)
    assert ic.recommendation_ar.startswith("ثقة شبه معدومة")


def test_composite_single_source_reason_when_score_below_half():
    # مصدر واحد بلا تأكيد ميداني ⇒ score=0.5 (غير <0.5)؛ لإثارة السبب نحتاج <0.5،
    # وهو غير ممكن من SourceConfidence وحده — نتحقّق فقط أنّ السبب غائب عند 0.5.
    ic = IndicatorConfidence(
        "NDVI",
        0.6,
        CloudConfidence(cloud_pct=0),
        TemporalConfidence(days_since_observation=0),
        CoverageConfidence(pixels_observed=100, pixels_expected=100),
        SourceConfidence(source_count=1),
    )
    assert all("مصدر واحد" not in r for r in ic.reasons_ar)


def test_to_dict_structure_and_rounded_components():
    ic = IndicatorConfidence(
        "NDVI",
        0.7,
        CloudConfidence(cloud_pct=0),
        TemporalConfidence(days_since_observation=2),
        CoverageConfidence(pixels_observed=100, pixels_expected=100),
        SourceConfidence(source_count=1),
    )
    d = ic.to_dict()
    assert d["indicator"] == "NDVI"
    assert d["value"] == 0.7
    assert set(d["confidence"]["components"].keys()) == {"cloud", "temporal", "coverage", "source"}
    assert d["confidence"]["level"] == ic.level.value
    assert d["confidence"]["components"]["source"] == 0.5


# ─── compute_ndvi_confidence: الواجهة المُبسَّطة ──────────────────────────────


def test_compute_ndvi_confidence_basic_wiring():
    now = datetime(2026, 6, 16, tzinfo=UTC)
    obs = now - timedelta(days=2)
    ic = compute_ndvi_confidence(0.65, obs, field_area_ha=1.0, now=now)
    assert ic.indicator_name == "NDVI"
    assert ic.measurement_value == 0.65
    assert ic.cloud.score == 1.0  # لا سحب افتراضاً
    assert ic.temporal.days_since_observation == 2
    # 1 هكتار = 10000 م² ÷ 100 م²/بكسل = 100 بكسل متوقّع.
    assert ic.coverage.pixels_expected == 100
    assert ic.source.source_count == 1


def test_compute_ndvi_confidence_clamps_negative_age():
    # تاريخ مستقبلي ⇒ days يُقصَر إلى 0 (ثقة زمنيّة كاملة).
    now = datetime(2026, 6, 16, tzinfo=UTC)
    future_obs = now + timedelta(days=3)
    ic = compute_ndvi_confidence(0.5, future_obs, field_area_ha=2.0, now=now)
    assert ic.temporal.days_since_observation == 0
    assert ic.temporal.score == 1.0
    assert ic.coverage.pixels_expected == 200  # 2 هكتار


def test_compute_ndvi_confidence_cloud_and_ground_truth():
    now = datetime(2026, 6, 16, tzinfo=UTC)
    obs = now - timedelta(days=1)
    ic = compute_ndvi_confidence(
        0.4, obs, field_area_ha=1.0, cloud_pct=30, has_ground_truth=True, now=now
    )
    assert ic.cloud.cloud_pct == 30
    assert ic.cloud.valid_pixel_pct == 70  # 100 - 30
    assert ic.source.has_ground_truth is True
    assert ic.source.score == pytest.approx(0.7)  # base 0.5 + 0.2
