"""Change-direction policy: stress indices are higher = worse; context-dependent ones get no verdict.

MSI (SWIR/NIR), CWSI and TVDI rise with water stress/dryness by definition, so an increase
is degradation. Bare-soil/tillage/brightness indices and LST change meaning with context
(tillage, harvest, season), so the pixel difference is kept but no improved/degraded label
is issued.
"""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")

import change_detection as cd  # noqa: E402
import tile_render  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("index", ["msi", "cwsi", "tvdi"])
def test_stress_index_increase_is_degradation(index):
    res = cd.detect_change([[0.2, 0.5]], [[0.6, 0.5]], index=index.upper())
    assert res["direction"] == "higher_is_worse"
    assert cd.index_direction(index) == "higher_is_worse"
    assert res["change_grid"] == [[cd.CODE_SEVERE_DEGRADATION, cd.CODE_STABLE]]
    assert res["degraded_pct"] == 50.0 and res["improved_pct"] == 0.0
    assert res["verdict_withheld"] is False
    assert "ملوحة" not in res["interpretation_ar"]


@pytest.mark.parametrize("index", ["msi", "cwsi", "tvdi"])
def test_stress_index_decrease_is_improvement(index):
    res = cd.detect_change([[0.6]], [[0.2]], index=index)
    assert res["change_grid"] == [[cd.CODE_IMPROVEMENT]]


@pytest.mark.parametrize("index", ["bsi", "bi", "bi2", "dbsi", "ndti", "lst"])
def test_context_dependent_index_keeps_delta_and_withholds_verdict(index):
    res = cd.detect_change([[0.1, 0.4, None]], [[0.5, 0.42, 0.3]], index=index)
    assert cd.index_direction(index) == "context_dependent"
    assert res["direction"] == "context_dependent"
    assert res["status"] == "assessed"
    assert res["verdict_withheld"] is True
    assert res["verdict_reason_codes"] == ["index_direction_context_dependent"]
    assert res["delta_grid"] == [[0.4, 0.02, None]]
    assert res["stats"]["max_delta"] == 0.4
    assert res["change_grid"] is None and res["zones"] == []
    assert res["improved_pct"] is None and res["degraded_pct"] is None
    assert res["areas"] is None and res["degraded_grid_pct"] is None
    assert res["stable_pct"] == 50.0 and res["changed_pct"] == 50.0
    assert "لا حكم عامّ" in res["interpretation_ar"]


def test_context_dependent_without_common_pixels_is_not_assessable():
    res = cd.detect_change([[None]], [[0.3]], index="lst")
    assert res["status"] == "not_assessable"
    assert res["changed_pct"] is None and res["stable_pct"] is None


def test_direction_classes_are_disjoint_and_cover_the_boundary_names():
    from raster_api_models import _CHANGE_INDEXES

    h, lo, ctx = cd._HIGHER_IS_WORSE, cd._LOWER_IS_WORSE, cd._CONTEXT_DEPENDENT
    assert not (h & lo) and not (h & ctx) and not (lo & ctx)
    assert h | lo | ctx == _CHANGE_INDEXES


def test_renderer_invert_matches_higher_is_worse_for_stress_indices():
    for index in ("msi", "cwsi", "tvdi", "salinity", "ndsi"):
        assert tile_render._INDEX_DOMAIN[index][2] is True, index
