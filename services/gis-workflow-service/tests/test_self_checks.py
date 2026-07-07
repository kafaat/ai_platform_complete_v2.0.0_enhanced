"""تحقّق — الفحوص الذاتيّة الحقيقيّة (الشريحة B): CRS/تاريخ/قيمة + تصنيف الأهمّية."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from self_checks import run_self_checks  # noqa: E402

pytestmark = pytest.mark.unit

_SPEC = {"analysis": {"index": "ndvi"}, "target": {"type": "field", "field_id": "f"}}
_META_OK = {
    "crs": "EPSG:4326",
    "resolution_m": 10,
    "acquisition_date": "2026-06-01",
    "valid_pixel_ratio": 0.9,
}
_STATS_OK = {
    "min": -0.1,
    "max": 0.8,
    "nodata_ratio": 0.05,
    "valid_pixel_ratio": 0.95,
    "shape": [4, 4],
}


def _by(sc, name):
    return next(c for c in sc["checks"] if c["name"] == name)


def test_all_good_passes():
    sc = run_self_checks(_SPEC, _META_OK, _STATS_OK)
    assert sc["passed"] is True and sc["quality"] == "good"


def test_missing_crs_is_required_failure():
    meta = dict(_META_OK)
    del meta["crs"]
    sc = run_self_checks(_SPEC, meta, _STATS_OK)
    assert _by(sc, "crs_present")["passed"] is False
    assert sc["passed"] is False and sc["quality"] == "failed"


def test_missing_acquisition_date_degrades_quality_not_failure():
    meta = dict(_META_OK)
    del meta["acquisition_date"]
    sc = run_self_checks(_SPEC, meta, _STATS_OK)
    assert _by(sc, "acquisition_date_present")["passed"] is False
    assert sc["passed"] is True  # لا يُفشِل (quality فقط)
    assert sc["quality"] == "degraded"


def test_ndvi_out_of_range_is_required_failure():
    stats = dict(_STATS_OK, max=5.0)  # خارج [-1,1]
    sc = run_self_checks(_SPEC, _META_OK, stats)
    assert _by(sc, "value_range")["passed"] is False
    assert sc["quality"] == "failed"


def test_unmeasurable_checks_are_skipped_not_fabricated():
    # بلا إحصاءات: value_range/nodata متخطّاة (passed=None) لا مُفتعَلة.
    sc = run_self_checks(_SPEC, _META_OK, {})
    assert _by(sc, "value_range")["passed"] is None
    assert _by(sc, "nodata_ratio")["passed"] is None
