"""Contract from the raster facade, through the auth-scoped context pack, to the zoning tool."""

from datetime import date, timedelta

import pytest
from api.routers import field_ai_context as ctx

from services.ai_agronomist.runtime_evidence import zoning_evidence_context

DAY = date.today().isoformat()
GRID = [[0.2, None], [0.6, 0.7]]
IDENTITY = {
    "rows": 2,
    "cols": 2,
    "crs": "EPSG:4326",
    "transform": [0.01, 0, 44.0, 0, -0.01, 16.0],
    "geometry_revision": 8,
}
BBOX = [44.0, 15.98, 44.02, 16.0]


def install(monkeypatch, *, change=None, absent=()):
    calls = []

    async def dates(field_id, *, tenant_id, index, limit):
        assert (field_id, tenant_id) == ("wheat", "tenant")
        return {"dates": [{"date": DAY, "has_cog": index not in absent}]}

    async def grid(field_id, *, tenant_id, index, date, grid, timeout_s):
        calls.append((index, date))
        assert field_id == "wheat" and tenant_id == "tenant" and grid == 16
        payload = {
            "field_id": field_id,
            "real_data": True,
            "index": index,
            "date": DAY,
            "bbox": BBOX,
            "grid": GRID,
            "grid_identity": IDENTITY,
            "valid_pixel_ratio": 0.8,
            "indicator_product": {
                "quality_gate_passed": True,
                "estimated": False,
                "field_id": field_id,
                "index": index,
                "source": "raster-service",
                "real_data": True,
                "provenance": {"scene_id": "S2-scene", "acquisition_datetime": DAY},
            },
        }
        if change:
            change(index, payload)
        return payload

    monkeypatch.setattr(ctx, "get_available_dates", dates)
    monkeypatch.setattr(ctx, "get_indicator_grid", grid)
    return calls


@pytest.mark.asyncio
async def test_observed_zoning_grids_reach_runtime_with_per_product_identity(monkeypatch):
    calls = install(monkeypatch)
    timeline, warning = await ctx._optional_imagery_timeline("wheat", "tenant", 30)
    assert warning is None
    assert sorted(calls) == sorted(
        [("ndvi", "latest"), ("ndmi", DAY), ("reci", DAY), ("msavi", DAY)]
    )
    pack = zoning_evidence_context({"imagery_timeline": timeline})
    assert set(pack["grid_metadata"]) == {"ndmi", "reci", "msavi", "ndvi"}
    for index, meta in pack["grid_metadata"].items():
        assert pack[f"{index}_grid"] == GRID
        assert meta == {
            "grid_identity": IDENTITY,
            "bbox": BBOX,
            "scene_id": "S2-scene",
            "acquisition_date": DAY,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "broken", ["field", "index", "scene", "day", "affine", "quality", "identity", "offline"]
)
async def test_unusable_layer_is_omitted_without_losing_master_or_other_grid(monkeypatch, broken):
    def change(index, payload):
        if index != "ndmi":
            return
        if broken == "field":
            payload["field_id"] = "other-field"
        elif broken == "index":
            payload["index"] = "ndre"
        elif broken == "scene":
            payload["indicator_product"]["provenance"]["scene_id"] = "S2-other"
        elif broken == "day":
            payload["indicator_product"]["provenance"]["acquisition_datetime"] = (
                date.today() - timedelta(days=1)
            ).isoformat()
        elif broken == "affine":
            payload["grid_identity"] = {**IDENTITY, "transform": [0.01, 0, 44.1, 0, -0.01, 16]}
        elif broken == "quality":
            payload["indicator_product"]["quality_gate_passed"] = False
        elif broken == "identity":
            del payload["grid_identity"]
        else:
            raise TimeoutError()

    calls = install(monkeypatch, change=change, absent={"reci"})
    timeline, warn = await ctx._optional_imagery_timeline("wheat", "tenant", 30)
    assert "ndmi_grid" in warn
    assert all(index != "reci" for index, day in calls)
    pack = zoning_evidence_context(
        {"imagery_timeline": timeline, "ndmi_grid": [["other"]], "grid_metadata": {"ndmi": {}}}
    )
    assert set(pack["grid_metadata"]) == {"ndvi", "msavi"}
    assert "ndmi_grid" not in pack and "reci_grid" not in pack


@pytest.mark.asyncio
async def test_missing_ndvi_quality_gate_prevents_auxiliary_reads(monkeypatch):
    calls = install(monkeypatch, change=lambda i, p: p.pop("indicator_product"))
    timeline, warn = await ctx._optional_imagery_timeline("wheat", "tenant", 30)
    assert "ndvi_grid" in warn
    assert calls == [("ndvi", "latest")]
    assert "grid_metadata" not in timeline and "ndvi_grid" not in timeline


@pytest.mark.asyncio
async def test_raster_reader_to_zoning_pack_keeps_real_affine_and_distinct_values(
    monkeypatch, tmp_path
):
    from pathlib import Path
    from types import SimpleNamespace

    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "services/raster-service"))
    import layer_lookup

    names = ["ndvi", "ndmi", "msavi", "reci"]
    for i, name in enumerate(names):
        # Small test GeoTIFF, read through the same COG reader as indicator-grid.
        with rasterio.open(
            tmp_path / f"{name}.tif",
            "w",
            driver="GTiff",
            width=4,
            height=3,
            count=1,
            crs="EPSG:4326",
            dtype="float32",
            transform=from_origin(44, 16, 0.01, 0.01),
        ) as dst:
            dst.write(np.full((3, 4), 0.1 * (i + 1), dtype="float32"), 1)

    async def grid(field_id, *, tenant_id, index, date, grid, timeout_s):
        assert field_id == "wheat" and tenant_id == "tenant"
        layer = {
            "field_id": field_id,
            "cog_url": str(tmp_path / f"{index}.tif"),
            "scene_id": "observed-scene",
            "acquisition_date": DAY,
            "geometry_revision": 2,
            "valid_pixel_ratio": 1.0,
        }
        return layer_lookup.grid_from_cog(
            layer, index, DAY, grid, SimpleNamespace(to_gdal_path=str)
        )

    install(monkeypatch)
    monkeypatch.setattr(ctx, "get_indicator_grid", grid)
    timeline, warn = await ctx._optional_imagery_timeline("wheat", "tenant", 30)
    assert warn is None
    observed = zoning_evidence_context({"imagery_timeline": timeline})
    for i, name in enumerate(names):
        assert observed[f"{name}_grid"][1][2] == pytest.approx(0.1 * (i + 1))
        meta = observed["grid_metadata"][name]
        assert meta["scene_id"] == "observed-scene"
        assert meta["bbox"] == [44, 15.97, 44.04, 16]
        assert meta["grid_identity"] == {
            "rows": 3,
            "cols": 4,
            "crs": "EPSG:4326",
            "geometry_revision": 2,
            "transform": [0.01, 0, 44, 0, -0.01, 16],
        }
