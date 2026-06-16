"""اختبارات سلوكيّة نقيّة لمنطق مرشد أخذ عيّنات التربة (zone sampling).

⚠️ ملاحظة دقيقة: ملفّ services/sahool-platform/api/zone_sampling.py لا يحتوي
أيّ منطق «تقسيم الحقل إلى 9 اتّجاهات/أزيموث/شبكة مكانيّة». الوحدة الفعليّة
دالّتان نقيّتان حتميّتان:

  - recommend_sampling_strategy(area_ha, has_field_history, variability)
      تختار «zone» مقابل «grid/grid_coarse» وتحسب عدد المناطق/العيّنات.
  - sampling_depth_advice(crop) تختار عمق العيّنة حسب جذور المحصول.

هذه الاختبارات تتحقّق من السلوك الحقيقيّ المُستنتَج بتشغيل الدالّتين (لا
من سلوك مُتخيَّل). التقسيم المكانيّ (k-means على صور القمر) مؤجّل صراحةً
في الكود تحت المفتاح deferred.auto_zoning.
"""

import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

from api.zone_sampling import (  # noqa: E402, I001
    recommend_sampling_strategy,
    sampling_depth_advice,
)


# ---------------------------------------------------------------------------
# اختيار النوع (method): zone مقابل grid/grid_coarse
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("variability", ["medium", "high"])
def test_history_plus_variability_selects_zone(variability):
    """تاريخ بالحقل + تباين متوسّط/عالٍ → method == 'zone'."""
    out = recommend_sampling_strategy(50, has_field_history=True, variability=variability)
    assert out["method"] == "zone"
    assert out["recommended_zones"] is not None


def test_low_variability_selects_grid_coarse_regardless_of_history():
    """تباين منخفض → grid_coarse بغضّ النظر عن التاريخ."""
    assert (
        recommend_sampling_strategy(50, has_field_history=True, variability="low")["method"]
        == "grid_coarse"
    )
    assert (
        recommend_sampling_strategy(50, has_field_history=False, variability="low")["method"]
        == "grid_coarse"
    )


def test_no_history_defaults_to_grid():
    """بلا تاريخ كافٍ (وبلا تباين منخفض) → grid."""
    assert recommend_sampling_strategy(50, has_field_history=False)["method"] == "grid"


def test_history_but_unknown_variability_is_grid():
    """تاريخ موجود لكن التباين 'unknown' → لا يرتقي إلى zone، يبقى grid."""
    out = recommend_sampling_strategy(50, has_field_history=True, variability="unknown")
    assert out["method"] == "grid"


def test_full_method_selection_matrix():
    """مصفوفة كاملة لاختيار النوع — السلوك الفعليّ المُستنتَج من الكود."""
    expected = {
        (True, "low"): "grid_coarse",
        (True, "medium"): "zone",
        (True, "high"): "zone",
        (True, "unknown"): "grid",
        (False, "low"): "grid_coarse",
        (False, "medium"): "grid",
        (False, "high"): "grid",
        (False, "unknown"): "grid",
    }
    for (history, var), method in expected.items():
        out = recommend_sampling_strategy(50, has_field_history=history, variability=var)
        assert out["method"] == method, f"history={history} var={var}"


# ---------------------------------------------------------------------------
# عدد المناطق (zone): مُقيَّد ضمن [3, 6] عبر round(area_ha / 15)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "area_ha,expected_zones",
    [
        (0, 3),  # حدّ أدنى max(3, ...)
        (10, 3),
        (45, 3),
        (52.5, 4),  # round(3.5)=4 (banker's: 3.5→4)
        (60, 4),
        (68, 5),  # round(4.53)=5
        (75, 5),
        (82.5, 6),  # round(5.5)=6
        (90, 6),
        (150, 6),  # حدّ أعلى min(6, ...)
    ],
)
def test_zone_count_clamped_between_3_and_6(area_ha, expected_zones):
    """عدد المناطق = clamp(round(area_ha/15), 3, 6) — حدود حقيقيّة."""
    out = recommend_sampling_strategy(area_ha, has_field_history=True, variability="high")
    assert out["recommended_zones"] == expected_zones
    # عيّنة مركّبة واحدة لكلّ منطقة
    assert out["recommended_samples"] == expected_zones


def test_zone_count_always_within_bounds_over_range():
    """فحص شامل: 3 <= zones <= 6 لأيّ مساحة في zone."""
    for area_ha in range(0, 500, 7):
        out = recommend_sampling_strategy(area_ha, has_field_history=True, variability="high")
        assert 3 <= out["recommended_zones"] <= 6


def test_zone_uses_composite_cores():
    """zone يستعمل عيّنة مركّبة من 8 cores."""
    out = recommend_sampling_strategy(50, has_field_history=True, variability="high")
    assert out["cores_per_composite"] == 8


# ---------------------------------------------------------------------------
# عدد العيّنات (grid): max(4, round(area_ha)) — ~عيّنة/هكتار
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "area_ha,expected_samples",
    [
        (0, 4),  # حدّ أدنى
        (1, 4),
        (4, 4),
        (5, 5),
        (10, 10),
        (50, 50),
        (99.4, 99),  # round(99.4)=99
        (100, 100),
    ],
)
def test_grid_sample_count(area_ha, expected_samples):
    """grid ≈ عيّنة لكلّ هكتار بحدّ أدنى 4."""
    out = recommend_sampling_strategy(area_ha, has_field_history=False)
    assert out["method"] == "grid"
    assert out["recommended_samples"] == expected_samples
    assert out["recommended_zones"] is None
    assert out["cores_per_composite"] == 1


def test_zone_saves_cost_versus_grid():
    """الميزة الفارقة: zone أقلّ تحاليل مخبريّة بكثير من grid لنفس المساحة."""
    area = 50
    zone = recommend_sampling_strategy(area, has_field_history=True, variability="high")
    grid = recommend_sampling_strategy(area, has_field_history=False)
    assert zone["recommended_samples"] < grid["recommended_samples"]


# ---------------------------------------------------------------------------
# سلامة المخرجات: المفاتيح، الوسم الإرشاديّ، تأجيل التقسيم التلقائيّ
# ---------------------------------------------------------------------------


def test_output_contract_keys_present():
    """عقد المخرجات يحوي كلّ المفاتيح المتوقَّعة."""
    out = recommend_sampling_strategy(50, has_field_history=True, variability="high")
    for key in (
        "method",
        "rationale_ar",
        "recommended_zones",
        "recommended_samples",
        "cores_per_composite",
        "note_ar",
        "is_estimate",
        "calibration_advice_ar",
        "deferred",
    ):
        assert key in out


def test_marked_as_estimate_and_auto_zoning_deferred_honestly():
    """موسوم إرشاديّ (is_estimate) + k-means التلقائيّ مؤجّل بصدق."""
    out = recommend_sampling_strategy(50, has_field_history=True, variability="high")
    assert out["is_estimate"] is True
    assert "auto_zoning" in out["deferred"]


def test_note_reports_actual_zone_count():
    """نصّ note_ar يعكس عدد المناطق المحسوب فعليّاً."""
    out = recommend_sampling_strategy(90, has_field_history=True, variability="high")
    assert str(out["recommended_zones"]) in out["note_ar"]


# ---------------------------------------------------------------------------
# عمق أخذ العيّنة حسب جذور المحصول
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("crop", ["alfalfa", "sorghum", "faba_bean", "cowpea"])
def test_deep_root_crops_get_two_depths(crop):
    """المحاصيل عميقة الجذور → عيّنتان (سطحيّة 0-30 + عميقة 30-60)."""
    out = sampling_depth_advice(crop)
    assert out["depths_cm"] == ["0-30 سم", "30-60 سم"]


@pytest.mark.parametrize("crop", ["wheat", "maize", "barley", None])
def test_shallow_or_unknown_crops_get_single_depth(crop):
    """المحاصيل غير المُدرجة أو None → عمق قياسيّ واحد 0-30 سم."""
    out = sampling_depth_advice(crop)
    assert out["depths_cm"] == ["0-30 سم"]


def test_depth_advice_marked_estimate():
    """نصيحة العمق موسومة إرشاديّة."""
    assert sampling_depth_advice("wheat")["is_estimate"] is True
