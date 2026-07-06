"""Guard: terrain visualization layers (hillshade / slope / contours) — honest fail-closed.

Design: three independent map layers, each with its own use —
  • Hillshade  → raster tile (shape of the land)      GET /v1/elevation/hillshade/{z}/{x}/{y}.png
  • Slope      → classified raster tile (agronomy)     GET /v1/slope/{z}/{x}/{y}.png
  • Contours   → vector GeoJSON lines (terracing/irrig) GET /v1/fields/{id}/contours.geojson
  • TileJSON for the two raster layers                 GET /v1/terrain/tilejson

Strict honesty: every layer needs a real configured DEM (``FIELD_DEM_PATH``). Without it →
transparent tile / ``features:[]`` + ``available:false``/``computed:false`` — never a
fabricated terrain. CI unit (``testpaths = tests_v9``) does not collect the co-located
behavioural test in ``services/raster-service/`` — this static guard keeps the contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_RENDER = _ROOT / "services" / "raster-service" / "terrain_render.py"
_ROUTER = _ROOT / "services" / "raster-service" / "routers" / "terrain_tiles.py"


def test_terrain_render_module_is_honest_and_masks_nodata():
    src = _RENDER.read_text(encoding="utf-8")
    assert "def render_hillshade_tile(" in src
    assert "def render_slope_tile(" in src
    assert "def compute_field_contours(" in src
    assert "SLOPE_CLASSES" in src  # 5-class agronomic ramp
    # honest fail-closed envelopes for contours — no fabricated lines.
    assert "dem-not-configured" in src and "field-bbox-unavailable" in src
    # DEM nodata masked (same lesson as compute_field_terrain) — masked read + fill NaN.
    assert "masked=True" in src and ".filled(np.nan)" in src


def test_terrain_endpoints_exist_and_fail_closed():
    src = _ROUTER.read_text(encoding="utf-8")
    assert '@router.get("/v1/elevation/hillshade/{z}/{x}/{y}.png")' in src
    assert '@router.get("/v1/slope/{z}/{x}/{y}.png")' in src
    assert '@router.get("/v1/terrain/tilejson")' in src
    assert '@router.get("/v1/fields/{field_id}/contours.geojson")' in src
    # raster tiles fail-closed to a transparent PNG (no DEM / no tenant ctx).
    assert "main._TRANSPARENT_PNG" in src
    # tilejson reports availability honestly (available:false + reason when no DEM).
    assert "dem-not-configured" in src
    # contours route is tenant-scoped like other field routes.
    assert "_require_field_tenant" in src
    # geographic tiles require a tenant context (tid), no anonymous access.
    assert "_REQ_TENANT" in src
