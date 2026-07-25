"""Guard: the available-dates imagery contract exposes field-AOI cloud distinctly.

Owner decision (imagery contract, V8-05 family): a date option must carry BOTH the
scene-level cloud (whole STAC scene) and the AOI-clipped cloud over the field, as
separate values — never conflate them, and never exclude a date that is clean over
the field just because the whole scene is cloudy. `cloud_pct` is kept as a documented
legacy alias for the scene value; `aoi_cloud_pct = null` means "not computed", not 0%.

Static guard (no live DB): asserts the raster query selects aoi_cloud_pct and the
route surfaces the dual-value contract + derives quality from the field-appropriate
value. Prevents a regression that re-conflates scene and field cloud.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
DB_PERSIST = ROOT / "services" / "raster-service" / "db_persist.py"
ROUTE = ROOT / "services" / "raster-service" / "routers" / "fields.py"


def test_available_dates_query_selects_aoi_cloud() -> None:
    sql = DB_PERSIST.read_text(encoding="utf-8")
    # The distinct-date query must return the AOI cloud alongside the scene cloud.
    assert "a.aoi_cloud_pct" in sql, "list_available_asset_dates must select aoi_cloud_pct"
    assert "a.cloud_pct" in sql, "scene-level cloud_pct must remain in the query"


def test_route_exposes_scene_and_aoi_cloud_contract() -> None:
    src = ROUTE.read_text(encoding="utf-8")
    # Dual-value contract keys present in the emitted date record.
    for key in ('"scene_cloud_pct"', '"aoi_cloud_pct"', '"cloud_pct"'):
        assert key in src, f"available-dates record must carry {key}"
    # _add must accept an aoi_cloud_pct input and thread it from the DB row.
    assert "aoi_cloud_pct=None" in src, "_add must accept aoi_cloud_pct"
    assert 'aoi_cloud_pct=row.get("aoi_cloud_pct")' in src, "DB row aoi_cloud_pct must be passed"
    # Quality/clear derivation must prefer the field-AOI value when present (not scene alone).
    assert (
        'rec["aoi_cloud_pct"] if rec["aoi_cloud_pct"] is not None else rec["cloud_pct"]' in src
    ), "clear_pct/quality must derive from AOI cloud when computed, else scene cloud"
