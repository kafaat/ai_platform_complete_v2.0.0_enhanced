"""Unit — مقاييس جودة الصور النقيّة (v131 / v62.3-B) في raster-service.

يقفل الدوالّ النقيّة في ``quality_metrics``: نسبة البكسلات الصالحة، تقريب التغطية،
والأعلام الحتميّة — بلا قاعدة/rasterio/شبكة. حالات الحافّة: شبكة فارغة → None،
كلّها صالحة → 1.0، نصفها NaN → 0.5، علم الغيوم/البكسلات المتناثرة.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_RASTER = Path(__file__).resolve().parent.parent / "services" / "raster-service"
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

import quality_metrics as qm  # noqa: E402

pytestmark = pytest.mark.unit

NAN = float("nan")


# ── valid_pixel_ratio_from_grid ─────────────────────────────────────────
def test_empty_grid_returns_none():
    # صدق: لا خلايا ⇒ None (لا 0.0 مُفبرَك).
    assert qm.valid_pixel_ratio_from_grid([]) is None
    assert qm.valid_pixel_ratio_from_grid([[], []]) is None
    assert qm.valid_pixel_ratio_from_grid(None) is None


def test_all_valid_ratio_is_one():
    grid = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert qm.valid_pixel_ratio_from_grid(grid) == 1.0


def test_half_nan_ratio_is_half():
    grid = [[0.1, NAN], [0.2, NAN]]
    assert qm.valid_pixel_ratio_from_grid(grid) == 0.5


def test_none_and_inf_and_nodata_are_invalid():
    grid = [[0.5, None, float("inf")], [-float("inf"), 0.7, -9999.0]]
    # صالحة: 0.5 و0.7 فقط (nodata=-9999) ⇒ 2/6.
    r = qm.valid_pixel_ratio_from_grid(grid, nodata=-9999.0)
    assert r == pytest.approx(2 / 6)


def test_numpy_array_supported_if_available():
    np = pytest.importorskip("numpy")
    arr = np.array([[1.0, np.nan], [2.0, 3.0]])
    assert qm.valid_pixel_ratio_from_grid(arr) == 0.75


def test_flat_grid_supported():
    assert qm.valid_pixel_ratio_from_grid([1.0, NAN, 2.0, 3.0]) == 0.75


# ── compute_quality_metrics: بوّابة النسب والأعلام ──────────────────────
def test_empty_grid_metrics_are_none_not_zero():
    m = qm.compute_quality_metrics(grid=[], cloud_pct=10.0)
    assert m["valid_pixel_ratio"] is None
    assert m["coverage_ratio"] is None
    # لا علم بكسلات متناثرة عند نسبة None (لا نعلّم ما لا نعرف).
    assert "sparse_valid_pixels" not in m["index_quality_flags"]


def test_coverage_defaults_to_valid_ratio_approximation():
    m = qm.compute_quality_metrics(grid=[[1.0, NAN], [1.0, 1.0]], cloud_pct=0.0)
    assert m["valid_pixel_ratio"] == 0.75
    assert m["coverage_ratio"] == 0.75  # تقريب صادق موثّق


def test_explicit_coverage_overrides_approximation():
    m = qm.compute_quality_metrics(grid=[[1.0, 1.0], [1.0, 1.0]], coverage_ratio=0.4, cloud_pct=0.0)
    assert m["valid_pixel_ratio"] == 1.0
    assert m["coverage_ratio"] == 0.4


def test_high_cloud_flag_above_threshold():
    m = qm.compute_quality_metrics(grid=[[1.0]], cloud_pct=40.0)
    assert "high_cloud" in m["index_quality_flags"]


def test_no_high_cloud_flag_at_or_below_threshold():
    m = qm.compute_quality_metrics(grid=[[1.0]], cloud_pct=35.0)
    assert "high_cloud" not in m["index_quality_flags"]


def test_sparse_valid_pixels_flag_below_threshold():
    # نصف الخلايا صالحة (0.5 < 0.7) ⇒ علم التناثر.
    m = qm.compute_quality_metrics(grid=[[1.0, NAN]], cloud_pct=0.0)
    assert m["valid_pixel_ratio"] == 0.5
    assert "sparse_valid_pixels" in m["index_quality_flags"]


def test_dense_valid_pixels_no_sparse_flag():
    m = qm.compute_quality_metrics(grid=[[1.0, 1.0, 1.0, 1.0]], cloud_pct=0.0)
    assert m["index_quality_flags"] == []


def test_both_flags_deterministic_order():
    # نسبة 0.5 (تناثر) + غيوم 90 (عالية) ⇒ high_cloud قبل sparse_valid_pixels.
    m = qm.compute_quality_metrics(grid=[[1.0, NAN]], cloud_pct=90.0)
    assert m["index_quality_flags"] == ["high_cloud", "sparse_valid_pixels"]


def test_metrics_from_pixel_counts_writer_path():
    # مسار الكاتب: عدّادات بكسلات جاهزة من stats (لا شبكة).
    m = qm.compute_quality_metrics(valid_pixels=70, total_pixels=100, cloud_pct=0.0)
    assert m["valid_pixel_ratio"] == pytest.approx(0.7)
    assert m["coverage_ratio"] == pytest.approx(0.7)
    assert "sparse_valid_pixels" not in m["index_quality_flags"]  # 0.7 ليست < 0.7


def test_zero_total_pixels_is_none():
    m = qm.compute_quality_metrics(valid_pixels=0, total_pixels=0, cloud_pct=0.0)
    assert m["valid_pixel_ratio"] is None
    assert m["coverage_ratio"] is None


def test_ratios_are_bounded_0_1():
    for grid in ([[1.0]], [[NAN]], [[1.0, NAN, 1.0]]):
        m = qm.compute_quality_metrics(grid=grid, cloud_pct=0.0)
        r = m["valid_pixel_ratio"]
        assert r is None or (0.0 <= r <= 1.0 and not math.isnan(r))
