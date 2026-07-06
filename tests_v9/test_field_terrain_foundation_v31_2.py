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


def test_terrain_masks_nodata_and_uses_circular_aspect_mean():
    """Two correctness fixes must not regress (both bite only with a real DEM):

    - DEM nodata (‑32768/‑9999…) must be masked via ``masked=True``; np.isfinite alone
      treats an integer sentinel as a real elevation → garbage mean + fake slope.
    - ``dominant_aspect`` must use a CIRCULAR mean (atan2 of mean sin/cos); a linear
      mean of angles straddling 0/360 returns the opposite compass direction.
    """
    src = _TERRAIN.read_text(encoding="utf-8")
    assert "masked=True" in src and ".filled(np.nan)" in src, "DEM nodata must be masked"
    # circular mean, not a bare av.mean() on aspect angles.
    assert "np.sin(ar)" in src and "np.cos(ar)" in src and "arctan2" in src
    assert "av.mean()" not in src, "linear mean of circular aspect is wrong"


def test_terrain_agronomy_interpretation_is_honest_and_fail_closed():
    """Slope→decisions bridge (erosion/trafficability/actions) must not fabricate:
    it returns None unless terrain is actually computed from a DEM."""
    src = _TERRAIN.read_text(encoding="utf-8")
    assert "def interpret_terrain_for_agronomy(" in src
    assert "erosion_risk" in src and "trafficability_risk" in src and "recommended_actions" in src
    # honest: no interpretation without computed terrain (no DEM ⇒ no decision).
    assert 'not terrain.get("computed")' in src
    # slope % from degrees (not raw degrees) for agronomic thresholds.
    assert "math.tan(math.radians(" in src
    # wired into the field terrain endpoint.
    rfields = (_ROOT / "services" / "raster-service" / "routers" / "fields.py").read_text(
        encoding="utf-8"
    )
    assert "interpret_terrain_for_agronomy" in rfields


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
