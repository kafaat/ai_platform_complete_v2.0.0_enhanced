"""Guard: SoilGrids soil-property raster layer — honest, disclaimer-bound, fail-closed.

A visual soil-property layer (SoilGrids/ISRIC) for *sampling guidance only* — never a
replacement for lab analysis (SoilGrids is ~250 m, insufficient inside a 1–2 ha field).
Requires a configured raster source (``SOILGRIDS_DIR``); without it → transparent tile +
``available:false`` + reason. A mandatory disclaimer is always attached. CI unit
(``testpaths = tests_v9``) does not collect the co-located behavioural test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_RENDER = _ROOT / "services" / "raster-service" / "soil_render.py"
_ROUTER = _ROOT / "services" / "raster-service" / "routers" / "soil_tiles.py"
_ZONES = _ROOT / "services" / "raster-service" / "soil_zones.py"


def test_soil_render_is_honest_and_disclaimer_bound():
    src = _RENDER.read_text(encoding="utf-8")
    assert "def render_soil_tile(" in src
    assert "SOIL_PROPERTIES" in src and "SOIL_DEPTHS" in src
    # real SoilGrids properties + unit-conversion factors (not invented units).
    for prop in ("phh2o", "clay", "sand", "soc", "cec"):
        assert f'"{prop}"' in src
    assert '"div"' in src  # stored→conventional unit divisor
    # mandatory disclaimer: guidance only, not a lab substitute.
    assert "DISCLAIMER_AR" in src and "لا تُغني عن التحليل المختبريّ" in src
    # honest source resolution — no fabricated soil values.
    assert "SOILGRIDS_DIR" in src


def test_soil_endpoints_exist_and_fail_closed_with_disclaimer():
    src = _ROUTER.read_text(encoding="utf-8")
    assert '@router.get("/v1/soil/tiles/{prop}/{depth}/{z}/{x}/{y}.png")' in src
    assert '@router.get("/v1/soil/tilejson")' in src
    assert '@router.get("/v1/soil/properties")' in src
    # transparent PNG when no source / no tenant context.
    assert "main._TRANSPARENT_PNG" in src
    # availability reported honestly + disclaimer always present in tilejson.
    assert "available" in src and "disclaimer" in src.lower()
    assert "soilgrids-source-not-configured" in src
    # geographic tiles require tenant context (tid) — no anonymous access.
    assert "_REQ_TENANT" in src


def test_field_soil_summary_and_zones_are_honest_and_tenant_scoped():
    render = _RENDER.read_text(encoding="utf-8")
    zones = _ZONES.read_text(encoding="utf-8")
    router = _ROUTER.read_text(encoding="utf-8")
    # per-field soil summary + USDA texture, fail-closed without source.
    assert "def compute_field_soil_summary(" in render
    assert "def usda_texture_class(" in render
    assert "soilgrids-source-not-configured" in render
    # sampling zones + points: numpy k-means, fail-closed, disclaimer.
    assert "def compute_soil_sampling_zones(" in zones
    assert "def compute_soil_sampling_points(" in zones  # points from real zone centroids
    assert "features.shapes" in zones or "rio_shapes" in zones  # polygonization
    assert '"computed": False' in zones and "DISCLAIMER_AR" in zones
    # field-scoped routes (tenant-guarded) — not anonymous.
    assert '@router.get("/v1/fields/{field_id}/soil/summary")' in router
    assert '@router.get("/v1/fields/{field_id}/soil/sampling-zones.geojson")' in router
    assert '@router.get("/v1/fields/{field_id}/soil/sampling-plan")' in router
    assert "_require_field_tenant" in router
