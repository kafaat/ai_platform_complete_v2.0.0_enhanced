"""تحقّق V63.6 — DEM: Copernicus مُفضَّل + ASTER احتياطيّ (DEM/NUM) + جودة NUM.

- Copernicus DEM هو DEM المُفضَّل (preferred_dem)، ASTER احتياطيّ — كلاهما active=False.
- ASTER يحمل products=[DEM,NUM] + requires_earthdata_login.
- dem_quality_from_num: كثافة NUM أعلى ⇒ ثقة أعلى؛ بلا NUM ⇒ unknown (لا تخمين).

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_RASTER = _ROOT / "services" / "raster-service"
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

import dem_quality as DQ  # noqa: E402
import raster_scene_model as M  # noqa: E402


# ── السِجِلّ: تفضيل Copernicus DEM ────────────────────────────────────────────────
def test_copernicus_dem_is_preferred_and_planned():
    assert M.preferred_dem() == "copernicus_dem"
    cop = M.PROVIDER_REGISTRY["copernicus_dem"]
    assert cop["active"] is False and cop["category"] == "dem" and cop["coverage_yemen"] is True


def test_aster_is_fallback_with_dem_num_products():
    a = M.PROVIDER_REGISTRY["aster_gdem"]
    assert a["preferred_dem"] is False
    assert a["products"] == ["DEM", "NUM"]
    assert a["requires_earthdata_login"] is True
    assert a["active"] is False


def test_dem_providers_lists_both_none_active():
    dems = M.dem_providers()
    assert "copernicus_dem" in dems and "aster_gdem" in dems
    assert all(d not in M.active_providers() for d in dems)


# ── جودة NUM ─────────────────────────────────────────────────────────────────────
def test_num_quality_high_when_dense():
    q = DQ.dem_quality_from_num([12, 14, 11, 13, 15])
    assert q["status"] == "present" and q["quality"] == "high"
    assert q["confidence"] > 0.8 and q["low_coverage_fraction"] == 0.0


def test_num_quality_low_when_sparse():
    q = DQ.dem_quality_from_num([1, 0, 2, 1, 0])  # كثافة منخفضة + تغطية ضعيفة عالية
    assert q["quality"] == "low"
    assert q["confidence"] < 0.3


def test_num_quality_unknown_without_data():
    assert DQ.dem_quality_from_num([])["status"] == "unknown"
    assert DQ.dem_quality_from_num(None)["status"] == "unknown"
    # قيم مشوّهة/سالبة تُسقَط (لا اختلاق).
    assert DQ.dem_quality_from_num(["x", -3, None])["status"] == "unknown"


def test_num_quality_confidence_monotonic():
    dense = DQ.dem_quality_from_num([10, 10, 10, 10])["confidence"]
    sparse = DQ.dem_quality_from_num([2, 2, 2, 2])["confidence"]
    assert dense > sparse  # أكثر مشاهد ⇒ ثقة أعلى
