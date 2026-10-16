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


@pytest.mark.parametrize(
    "scene_cloud,aoi_cloud,expected_clear,expected_quality",
    [(90, 5, 95, "high"), (20, None, 80, "medium"), (None, None, None, None)],
)
def test_route_exposes_scene_and_aoi_cloud_contract(
    scene_cloud, aoi_cloud, expected_clear, expected_quality
) -> None:
    import importlib.util

    src = ROUTE.read_text(encoding="utf-8")
    assert "create_date_accumulator(" in src
    assert 'aoi_cloud_pct=row.get("aoi_cloud_pct")' in src
    path = ROOT / "services/raster-service/raster_available_dates.py"
    spec = importlib.util.spec_from_file_location("aoi_date_aggregation", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    records, add = helper.create_date_accumulator(
        display_index=str, high_quality_clear_pct=90, min_clear_pct=70
    )
    add("2026-10-15", cloud_pct=scene_cloud, aoi_cloud_pct=aoi_cloud, idx="ndvi")
    item = records["2026-10-15"]
    assert item["scene_cloud_pct"] == scene_cloud
    assert item["cloud_pct"] == scene_cloud
    assert item["aoi_cloud_pct"] == aoi_cloud
    assert item["clear_pct"] == expected_clear
    assert item["quality_label"] == expected_quality
