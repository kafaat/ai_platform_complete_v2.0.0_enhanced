"""Common valid mask: a field's trend is computed only over pixels valid in every scene.

Lesson from InSAR time series practice (DefoEye): a scene that is 70% cloud-masked and
covers another part of the field must not be averaged with full scenes, or a shift in
spatial coverage reads as a change over time. Synthetic arrays and GeoTIFFs only; no
network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

SERVICE_DIR = Path(__file__).resolve().parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import time_series as ts  # noqa: E402

# A 20×20 grid; the field is rows/cols 2..17 (16×16 = 256 pixels). The true index is
# 0.3 on the west half (col < 10) and 0.7 on the east half, identical in every scene.
SIZE, LO, HI = 20, 2, 18
FIELD = np.zeros((SIZE, SIZE), dtype=bool)
FIELD[LO:HI, LO:HI] = True
TRUTH = np.where(np.arange(SIZE)[None, :] < 10, 0.3, 0.7) * np.ones((SIZE, 1))


def _scene(col_from: int, col_to: int) -> np.ndarray:
    """The true field, valid only on cols [col_from, col_to) inside the field (NaN elsewhere)."""
    values = np.full((SIZE, SIZE), np.nan)
    keep = FIELD.copy()
    keep[:, :col_from] = False
    keep[:, col_to:] = False
    values[keep] = TRUTH[keep]
    return values


def _own_mean(values: np.ndarray) -> float:
    return float(np.nanmean(values))


def test_coverage_shift_gives_a_spurious_trend_only_without_the_common_mask():
    a, b = _scene(2, 14), _scene(6, 18)  # west-heavy in January, east-heavy in March
    old = ts.build_time_series(
        [
            {"datetime": "2026-01-10", "mean": _own_mean(a)},
            {"datetime": "2026-03-10", "mean": _own_mean(b)},
        ]
    )
    assert old["trend"]["direction"] == "improving"  # the old path reads coverage as growth

    new = ts.build_common_mask_series(
        [{"datetime": "2026-01-10", "values": a}, {"datetime": "2026-03-10", "values": b}],
        FIELD,
        field_mask_basis="saved_field_geometry",
    )
    assert new["trend"]["direction"] == "stable"
    assert new["trend"]["slope"] == 0
    cm = new["common_mask"]
    # common = cols 6..13 × rows 2..17 = 8 × 16
    assert cm["field_pixels"] == 256
    assert cm["common_valid_pixels"] == 128
    assert cm["common_coverage_ratio"] == 0.5
    assert cm["scenes_used"] == 2 and cm["scenes_excluded"] == 0
    assert [s["valid_pixels"] for s in cm["scenes"]] == [192, 192]
    assert [s["common_mean"] for s in cm["scenes"]] == [0.5, 0.5]


def test_disjoint_halves_are_declared_insufficient_not_a_number():
    a, b = _scene(2, 10), _scene(10, 18)
    new = ts.build_common_mask_series(
        [{"datetime": "2026-01-10", "values": a}, {"datetime": "2026-03-10", "values": b}],
        FIELD,
        field_mask_basis="saved_field_geometry",
    )
    assert new["trend"]["direction"] == "insufficient_common_coverage"
    assert new["trend"]["slope"] is None
    assert new["common_mask"]["common_valid_pixels"] == 0
    assert new["common_mask"]["status"] == "insufficient_common_coverage"
    assert new["anomalies"] == []


def test_below_threshold_coverage_is_declared():
    a, b = _scene(2, 14), _scene(6, 18)  # common coverage exactly 0.5
    new = ts.build_common_mask_series(
        [{"datetime": "2026-01-10", "values": a}, {"datetime": "2026-03-10", "values": b}],
        FIELD,
        field_mask_basis="saved_field_geometry",
        min_common_coverage=0.6,
    )
    trend = new["trend"]
    assert trend["direction"] == "insufficient_common_coverage"
    assert trend["slope"] is None
    assert trend["reason"] == "common_coverage_below_min"
    assert trend["common_coverage_ratio"] == 0.5 and trend["min_common_coverage"] == 0.6


def test_a_mostly_clouded_scene_is_excluded_with_its_reason():
    full = _scene(2, 18)
    cloudy = _scene(2, 6)  # 25% of the field valid
    new = ts.build_common_mask_series(
        [
            {"datetime": "2026-01-10", "values": full, "scene_id": "A"},
            {"datetime": "2026-02-10", "values": cloudy, "scene_id": "B"},
            {"datetime": "2026-03-10", "values": full, "scene_id": "C"},
        ],
        FIELD,
        field_mask_basis="saved_field_geometry",
    )
    cm = new["common_mask"]
    assert cm["scenes_used"] == 2 and cm["scenes_excluded"] == 1
    (excluded,) = cm["exclusions"]
    assert excluded["scene_id"] == "B"
    assert excluded["reason"] == "scene_valid_coverage_below_min"
    assert excluded["valid_coverage_ratio"] == 0.25
    assert cm["common_valid_pixels"] == 256 and cm["common_coverage_ratio"] == 1.0
    assert new["trend"]["direction"] == "stable"


def test_greedy_rule_drops_the_scene_that_shrinks_the_common_mask_most():
    # Each scene covers ≥ 50% of the field; one east-only scene empties the intersection.
    scenes = [
        {"datetime": "2026-01-10", "values": _scene(2, 16)},
        {"datetime": "2026-02-10", "values": _scene(4, 18)},
        {"datetime": "2026-03-10", "values": _scene(10, 18)},
        {"datetime": "2026-04-10", "values": _scene(2, 18)},
    ]
    new = ts.build_common_mask_series(scenes, FIELD, field_mask_basis="saved_field_geometry")
    cm = new["common_mask"]
    reasons = [s["reason"] for s in cm["scenes"]]
    assert reasons == [None, None, "shrinks_common_mask", None]
    assert cm["common_valid_pixels"] == 12 * 16  # cols 4..15
    assert cm["status"] == "ok"


def test_minimum_scene_count_stops_exclusion():
    new = ts.build_common_mask_series(
        [
            {"datetime": "2026-01-10", "values": _scene(2, 10)},
            {"datetime": "2026-03-10", "values": _scene(10, 18)},
        ],
        FIELD,
        field_mask_basis="saved_field_geometry",
    )
    assert new["common_mask"]["scenes_used"] == 2  # no exclusion below min_scenes=2


# ── route path: synthetic GeoTIFFs on different pixel grids, saved field geometry ──


def _write_tif(path: Path, values: np.ndarray, *, col_shift: int = 0) -> str:
    import rasterio
    from rasterio.transform import from_origin

    # 10 m UTM pixels; a positive col_shift starts the raster that many pixels further west
    # and pads it, so the scene is on a different pixel grid than the reference.
    data = np.full((SIZE, SIZE + col_shift), -9999.0, dtype="float32")
    data[:, col_shift:] = np.where(np.isfinite(values), values, -9999.0)
    transform = from_origin(500000.0 - 10.0 * col_shift, 1700000.0, 10.0, 10.0)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:32638",
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(data, 1)
    return str(path)


def _field_geometry() -> dict:
    from rasterio.warp import transform_geom

    x0, y0 = 500000.0 + 10.0 * LO, 1700000.0 - 10.0 * LO
    x1, y1 = 500000.0 + 10.0 * HI, 1700000.0 - 10.0 * HI
    ring = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]
    return transform_geom("EPSG:32638", "EPSG:4326", {"type": "Polygon", "coordinates": [ring]})


async def _route(monkeypatch, tmp_path, scenes, revisions=None, **kwargs):
    import db_persist
    from routers import fields

    grids = {}
    for date, values, shift in scenes:
        uri = _write_tif(tmp_path / f"{date}.tif", values, col_shift=shift)
        grids[date] = {
            "date": date,
            "stats": {"mean": _own_mean(values)},
            "grid_identity": {"geometry_revision": (revisions or {}).get(date, 4)},
            "indicator_product": {"provenance": {"scene_id": f"S2_{date}", "source_uri": uri}},
        }

    async def allow_field(field_id: str, **kw):
        return None

    async def real_grid(field_id, index, date, grid):
        return grids.get(date)

    async def saved_geometry(field_id, tenant_id=None):
        return {"geometry": _field_geometry(), "revision": 4}

    monkeypatch.setattr(fields, "_require_field_tenant", allow_field)
    monkeypatch.setattr(fields, "_real_field_grid", real_grid)
    monkeypatch.setattr(db_persist, "fetch_field_geometry_with_revision", saved_geometry)
    return await fields.field_timeseries(
        "field-1", index="ndvi", dates=",".join(grids), grid=16, **kwargs
    )


async def test_route_flag_uses_the_common_mask_and_keeps_the_old_keys(monkeypatch, tmp_path):
    scenes = [("2026-01-10", _scene(2, 14), 0), ("2026-03-10", _scene(6, 18), 3)]
    old = await _route(monkeypatch, tmp_path, scenes)
    assert old["trend"]["direction"] == "improving"
    assert "common_mask" not in old

    new = await _route(monkeypatch, tmp_path, scenes, common_mask=True)
    assert new["trend"]["direction"] == "stable" and new["trend"]["slope"] == 0
    assert new["unmasked_trend"]["direction"] == "improving"
    cm = new["common_mask"]
    assert cm["field_mask_basis"] == "saved_field_geometry"
    assert (cm["field_pixels"], cm["common_valid_pixels"]) == (256, 128)
    assert cm["common_coverage_ratio"] == 0.5
    # the field window rounds outward (geometry_window), so it may hold one extra edge pixel
    assert cm["grid"]["crs"] == "EPSG:32638" and 16 <= cm["grid"]["rows"] <= 17
    assert [p["common_mask_mean"] for p in new["points"]] == [0.5, 0.5]
    # existing keys keep their meaning
    assert [round(p["mean"], 4) for p in new["points"]] == [0.4333, 0.5667]
    assert new["available"] is True and new["real_data"] is True


async def test_route_declares_below_threshold_coverage(monkeypatch, tmp_path):
    scenes = [("2026-01-10", _scene(2, 14), 0), ("2026-03-10", _scene(6, 18), 0)]
    new = await _route(monkeypatch, tmp_path, scenes, common_mask=True, min_common_coverage=0.6)
    assert new["trend"]["direction"] == "insufficient_common_coverage"
    assert new["trend"]["slope"] is None
    assert new["common_mask"]["common_coverage_ratio"] == 0.5


async def test_route_excludes_a_scene_cut_with_another_boundary_revision(monkeypatch, tmp_path):
    full = _scene(2, 18)
    scenes = [("2026-01-10", full, 0), ("2026-02-10", full, 0), ("2026-03-10", full, 0)]
    new = await _route(monkeypatch, tmp_path, scenes, common_mask=True, revisions={"2026-02-10": 3})
    (excluded,) = new["common_mask"]["exclusions"]
    assert excluded["datetime"] == "2026-02-10"
    assert excluded["reason"] == "geometry_revision_mismatch"
    assert new["common_mask"]["scenes_used"] == 2
    assert new["common_mask"]["common_coverage_ratio"] == 1.0


async def test_route_declares_an_unavailable_mask_instead_of_falling_back(monkeypatch, tmp_path):
    import raster_field_coverage

    monkeypatch.setattr(
        raster_field_coverage,
        "align_scenes_to_field_grid",
        lambda *a, **k: {"error": "no_readable_scene"},
    )
    scenes = [("2026-01-10", _scene(2, 14), 0), ("2026-03-10", _scene(6, 18), 0)]
    new = await _route(monkeypatch, tmp_path, scenes, common_mask=True)
    assert new["trend"]["direction"] == "insufficient_common_coverage"
    assert new["trend"]["slope"] is None
    assert new["common_mask"]["status"] == "unavailable"
    assert new["common_mask"]["reason"] == "no_readable_scene"
    assert new["unmasked_trend"]["direction"] == "improving"
