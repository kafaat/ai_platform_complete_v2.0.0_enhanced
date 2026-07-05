"""Guard: field-terrain foundation (TERRAIN gap) — server route + honest fail-closed.

Closes the frontend TERRAIN stub's server-side gap: a tenant-scoped
GET /v1/fields/{id}/terrain (raster) proxied by the platform, computing elevation/
slope/aspect from a configured DEM (``FIELD_DEM_PATH``) clipped to the field bbox,
with an honest ``computed=false`` envelope when the DEM or bbox is absent — never a
fabricated terrain number. 3D terrain-RGB rendering stays a documented TODO.

CI unit (``testpaths = tests_v9``) does not collect the co-located behavioural test
in ``services/raster-service/`` — this static guard keeps the contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_TERRAIN = _ROOT / "services" / "raster-service" / "terrain_analysis.py"
_RASTER_FIELDS = _ROOT / "services" / "raster-service" / "routers" / "fields.py"
_PLATFORM_FIELDS = _ROOT / "services" / "sahool-platform" / "api" / "routers" / "fields.py"


def test_terrain_compute_helper_is_honest():
    src = _TERRAIN.read_text(encoding="utf-8")
    assert "def compute_field_terrain(" in src
    # Honest fail-closed sources — no fabricated stats.
    assert "dem-not-configured" in src
    assert "field-bbox-unavailable" in src
    assert "computed" in src


def test_raster_exposes_tenant_scoped_terrain_route():
    src = _RASTER_FIELDS.read_text(encoding="utf-8")
    assert '@router.get("/v1/fields/{field_id}/terrain")' in src
    assert "compute_field_terrain" in src
    assert "FIELD_DEM_PATH" in src
    # tenant-scoped like the other field GET routes.
    assert "_require_field_tenant" in src


def test_platform_terrain_enriches_from_dem_without_duplicate_route():
    src = _PLATFORM_FIELDS.read_text(encoding="utf-8")
    # Single terrain route (the pre-existing enrich endpoint) — no duplicate registration.
    assert src.count('@router.get("/api/v1/fields/{field_id}/terrain")') == 1
    # It fills terrain from the live-DEM compute (best-effort) via raster-service.
    assert "_compute_field_terrain_from_dem" in src
    assert "guard_field_geometry" in src
    assert "/v1/fields/{field_id}/terrain" in src  # raster-service call
    # honest 404 when the field is not the tenant's.
    assert "الحقل غير موجود ضمن هذا المستأجِر" in src
