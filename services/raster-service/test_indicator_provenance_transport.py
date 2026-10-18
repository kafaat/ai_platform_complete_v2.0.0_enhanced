"""Preserve measured producer metadata without inventing authority for old COGs."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import db_persist
import layer_lookup
import numpy as np
import pytest
import rasterio
from raster_indicator_product import from_grid_response
from rasterio.transform import from_origin

pytestmark = pytest.mark.unit

ACQUIRED = "2026-09-01"
AVAILABLE = "2026-09-03T08:30:00+00:00"
TENANT = "00000000-0000-0000-0000-000000000001"


def test_typed_grid_preserves_explicit_availability():
    product = from_grid_response(
        {
            "field_id": "fld_1",
            "index": "ndvi",
            "date": ACQUIRED,
            "real_data": True,
            "valid_pixel_ratio": 0.9,
            "data_available_at": AVAILABLE,
        }
    )
    assert product["data_available_at"] == AVAILABLE


def test_typed_grid_does_not_invent_availability():
    product = from_grid_response(
        {
            "field_id": "fld_1",
            "index": "ndvi",
            "date": ACQUIRED,
            "real_data": True,
            "valid_pixel_ratio": 0.9,
        }
    )
    assert product.get("data_available_at") is None


@pytest.mark.parametrize("recorded", [True, False])
def test_rehydration_preserves_metadata_without_timestamp_fallback(monkeypatch, recorded):
    asset = {"cog_url": "asset.tif", "acquisition_date": ACQUIRED}
    if recorded:
        asset.update(
            created_at=AVAILABLE,
            data_available_at=AVAILABLE,
            cloud_mask_applied=True,
            quality_score=0.72,
            algorithm_version="historic.algorithm/2",
            qa_mask_version="historic.mask/3",
        )

    async def fetch(*args, **kwargs):
        assert kwargs["tenant_id"] == TENANT
        return asset

    monkeypatch.setattr(db_persist, "fetch_latest_asset", fetch)
    layer = asyncio.run(
        layer_lookup.rehydrate_field_layer_from_db(
            "fld_1",
            "ndvi",
            "latest",
            layers={},
            field_layers={},
            tenant_getter=lambda: TENANT,
            logger=logging.getLogger(__name__),
            object_store_module=SimpleNamespace(exists_locally=lambda _: True),
        )
    )
    assert layer is not None
    for key in (
        "created_at",
        "data_available_at",
        "quality_score",
        "algorithm_version",
        "qa_mask_version",
    ):
        assert layer.get(key) == asset.get(key)


@pytest.mark.parametrize("recorded", [True, False])
def test_cog_grid_preserves_measured_quality_and_actual_algorithm(tmp_path, recorded):
    path = tmp_path / "index.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(44, 15, 0.01, 0.01),
    ) as dst:
        dst.write(np.full((2, 2), 0.5, dtype="float32"), 1)
    layer = {
        "cog_url": str(path),
        "field_id": "fld_1",
        "acquisition_date": ACQUIRED,
        "scene_id": "scene_1",
        "valid_pixel_ratio": 1.0,
    }
    if recorded:
        layer.update(
            created_at=AVAILABLE,
            data_available_at=AVAILABLE,
            cloud_mask_applied=True,
            quality_score=0.72,
            confidence=0.95,
            algorithm_version="historic.algorithm/2",
            qa_mask_version="historic.mask/3",
        )
    result = layer_lookup.grid_from_cog(
        layer, "ndvi", "latest", 2, SimpleNamespace(to_gdal_path=lambda x: x)
    )
    product = result["indicator_product"]
    assert product.get("data_available_at") == layer.get("data_available_at")
    assert product["quality_score"] == layer.get("quality_score")
    assert product["provenance"]["algorithm_version"] == layer.get("algorithm_version")
    assert product["provenance"]["qa_mask_version"] == layer.get("qa_mask_version")


def test_asset_reader_returns_stored_authority_fields_and_keeps_tenant_scope(monkeypatch):
    row = dict.fromkeys(
        (
            "minx",
            "miny",
            "maxx",
            "maxy",
            "confidence",
            "cloud_pct",
            "coverage_ratio",
            "quality_flags",
            "quality",
            "cloud_mask_applied",
            "geometry_revision",
            "processing_job_id",
            "srid",
        )
    )
    row.update(
        cog_uri="asset.tif",
        acq=ACQUIRED,
        valid_pixel_ratio=0.9,
        scene_id="scene_1",
        asset_status="ready",
        quality_score=0.72,
        algorithm_version="historic.algorithm/2",
        qa_mask_version="historic.mask/3",
        created_at=AVAILABLE,
        data_available_at=AVAILABLE,
        cloud_mask_applied=True,
    )

    class Conn:
        async def execute(self, sql, *args):
            assert args == (TENANT,)

        async def fetchrow(self, sql, *args):
            assert "tenant_id = $4::uuid" in sql
            assert args[-1] == TENANT
            return row

        async def close(self):
            pass

    async def connect():
        return Conn()

    monkeypatch.setattr(db_persist, "_connect", connect)
    result = asyncio.run(db_persist.fetch_latest_asset("fld_1", "ndvi", tenant_id=TENANT))
    assert result is not None
    for key in (
        "created_at",
        "data_available_at",
        "quality_score",
        "algorithm_version",
        "qa_mask_version",
    ):
        assert result.get(key) == row[key]


@pytest.mark.parametrize("provider", ["element84", None])
def test_persistence_preserves_only_explicit_provider(monkeypatch, provider):
    from raster_api_models import ProcessRequest
    from raster_asset_persistence import persist_raster_asset

    captured = {}

    async def insert(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(db_persist, "insert_raster_asset", insert)
    req = ProcessRequest(
        field_id="fld_1",
        tenant_id=TENANT,
        scene_id="scene_1",
        indicator="ndvi",
        source_format="sentinel2_l2a",
        bands={"red": 1, "nir": 2},
        provider=provider,
    )
    assert persist_raster_asset(
        req, "file:///scene.tif", {}, [44, 15, 45, 16], {"valid_pixels": 4, "nodata_pixels": 0}
    )
    assert "provider" in captured["provenance"]
    assert captured["provenance"]["provider"] == provider


@pytest.mark.parametrize("recorded", [True, False])
def test_new_layer_preserves_actual_processing_identities(recorded):
    from raster_api_models import JobStatus, ProcessRequest
    from raster_job_orchestration import run_processing

    stats = {"valid_pixels": 4, "nodata_pixels": 0}
    if recorded:
        stats["validated_raster_product"] = {
            "cloud_mask_applied": True,
            "provenance": {
                "algorithm_version": "actual.algorithm/2",
                "qa_mask_version": "actual.mask/4",
            },
        }
    jobs = {}
    ctx = SimpleNamespace(
        _jobs=SimpleNamespace(get=jobs.get, set=jobs.__setitem__),
        _layers={},
        _field_layers={},
        JobStatus=JobStatus,
        logger=logging.getLogger(__name__),
        _process_precomputed_pixels=lambda *_: (
            stats,
            [44, 15, 45, 16],
            10,
            {"cog_url": "file:///scene.tif"},
        ),
        _persist_raster_asset=lambda *args, **kwargs: True,
    )
    req = ProcessRequest(
        field_id="fld_1",
        tenant_id=TENANT,
        scene_id="scene_1",
        indicator="ndvi",
        source_format="sentinel2_l2a",
        bands={"red": 1, "nir": 2},
        provider="cdse",
        raster_url="file:///scene.tif",
        precomputed_index=True,
    )
    run_processing(ctx, "job_1", req)
    assert jobs["job_1"].get("publication_eligible") is True
    layer = next(iter(ctx._layers.values()))
    expected = (stats.get("validated_raster_product") or {}).get("provenance") or {}
    for key in ("algorithm_version", "qa_mask_version"):
        assert layer.get(key) == expected.get(key)


@pytest.mark.parametrize("applied", [True, False, None])
def test_persistence_and_rehydration_do_not_promote_requested_mask(monkeypatch, tmp_path, applied):
    from raster_api_models import ProcessRequest
    from raster_asset_persistence import persist_raster_asset

    path = tmp_path / "mask-check.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(44, 15, 0.01, 0.01),
    ) as dst:
        dst.write(np.full((2, 2), 0.5, dtype="float32"), 1)
    captured = {}

    async def insert(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(db_persist, "insert_raster_asset", insert)
    req = ProcessRequest(
        field_id="fld_1",
        tenant_id=TENANT,
        scene_id="scene_1",
        indicator="ndvi",
        source_format="sentinel2_l2a",
        bands={"red": 1, "nir": 2},
        provider="cdse",
        apply_cloud_mask=True,
    )
    stats = {
        "valid_pixels": 4,
        "nodata_pixels": 0,
        "confidence": 0.9,
        "validated_raster_product": {
            "cloud_mask_applied": applied,
            "provenance": {"qa_mask_version": "observed-scl/1" if applied else None},
        },
    }
    assert persist_raster_asset(req, path.as_uri(), {}, [44, 15, 45, 16], stats)
    assert captured["qa_mask_version"] == ("observed-scl/1" if applied else None)

    # Include a legacy row whose stored version was based solely on a request.
    async def fetch(*args, **kwargs):
        return {
            "cog_url": str(path),
            "acquisition_date": ACQUIRED,
            "scene_id": "scene_1",
            "valid_pixel_ratio": 1.0,
            "quality_score": 0.9,
            "qa_mask_version": captured["qa_mask_version"] or "cloud-mask/1",
            "cloud_mask_applied": captured["provenance"]["stats"]["cloud_mask_applied"],
        }

    monkeypatch.setattr(db_persist, "fetch_latest_asset", fetch)
    layer = asyncio.run(
        layer_lookup.rehydrate_field_layer_from_db(
            "fld_1",
            "ndvi",
            "latest",
            layers={},
            field_layers={},
            tenant_getter=lambda: TENANT,
            logger=logging.getLogger(__name__),
            object_store_module=SimpleNamespace(exists_locally=lambda _: True),
        )
    )
    result = layer_lookup.grid_from_cog(
        layer, "ndvi", "latest", 2, SimpleNamespace(to_gdal_path=lambda x: x)
    )
    assert result["indicator_product"]["provenance"]["qa_mask_version"] == (
        "observed-scl/1" if applied else None
    )


def test_reprocessing_same_identity_carries_current_cog_publication_time(monkeypatch):
    from raster_api_models import ProcessRequest
    from raster_asset_persistence import persist_raster_asset

    writes = []

    async def insert(**kwargs):
        writes.append(kwargs)
        return True

    monkeypatch.setattr(db_persist, "insert_raster_asset", insert)
    req = ProcessRequest(
        field_id="fld_1",
        tenant_id=TENANT,
        scene_id="scene_1",
        indicator="ndvi",
        source_format="sentinel2_l2a",
        bands={"red": 1, "nir": 2},
        provider="cdse",
    )
    times = ["2026-09-03T08:30:00+00:00", "2026-09-04T10:00:00+00:00"]
    for n, published in enumerate(times):
        assert persist_raster_asset(
            req,
            f"file:///scene-{n}.tif",
            {"data_available_at": published},
            [44, 15, 45, 16],
            {"valid_pixels": 4, "nodata_pixels": 0},
        )
    assert writes[0]["product_identity_key"] == writes[1]["product_identity_key"]
    assert writes[0]["cog_uri"] != writes[1]["cog_uri"]
    for write, published in zip(writes, times, strict=True):
        assert write["provenance"].get("data_available_at") == published


def test_legacy_created_at_is_not_availability_of_replaced_cog(tmp_path):
    path = tmp_path / "replaced.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(44, 15, 0.01, 0.01),
    ) as dst:
        dst.write(np.full((2, 2), 0.5, dtype="float32"), 1)
    result = layer_lookup.grid_from_cog(
        {"cog_url": str(path), "created_at": AVAILABLE, "valid_pixel_ratio": 1.0},
        "ndvi",
        "latest",
        2,
        SimpleNamespace(to_gdal_path=lambda x: x),
    )
    assert result["indicator_product"].get("data_available_at") is None


def test_real_cog_grid_supplies_change_identity_and_legacy_is_explicit(tmp_path, monkeypatch):
    import pytest
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from raster_api_models import ChangeDetectRequest
    from routers import analysis

    path = tmp_path / "aligned.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=5,
        width=7,
        count=1,
        dtype="float32",
        crs="EPSG:32638",
        transform=from_origin(400000, 1600000, 10, 10),
    ) as dst:
        dst.write(np.full((5, 7), 0.6, dtype="float32"), 1)
    layer = {"cog_url": str(path), "field_id": "fld_1", "geometry_revision": 3}
    product = layer_lookup.grid_from_cog(
        layer, "ndvi", "2026-07-01", 2, SimpleNamespace(to_gdal_path=lambda p: p)
    )
    ident = product["grid_identity"]
    assert ident == {
        "crs": "EPSG:32638",
        "transform": [35.0, 0.0, 400000.0, 0.0, -25.0, 1600000.0],
        "geometry_revision": 3,
        "rows": 2,
        "cols": 2,
    }
    data = dict(
        field_id="fld_1",
        date_before="2026-07-01",
        date_after="2026-07-03",
        grid_before=product["grid"],
        grid_after=[[0.3, 0.3], [0.3, 0.3]],
    )
    monkeypatch.setattr(analysis, "AGENT_TOKEN", "grid-test-token")
    app = FastAPI()
    app.include_router(analysis.router)
    client = TestClient(app)
    headers = {"X-Agent-Token": "grid-test-token"}
    legacy = client.post("/v1/change/detect", headers=headers, json=data)
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["status"] == "not_assessable"
    assert legacy.json()["change_grid"] is None
    response = client.post(
        "/v1/change/detect",
        headers=headers,
        json={**data, "grid_before_identity": ident, "grid_after_identity": ident},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "assessed"
    assert response.json()["degraded_pct"] == 100
    with pytest.raises(ValueError, match="spatial_identity_mismatch"):
        ChangeDetectRequest(
            **data,
            grid_before_identity=ident,
            grid_after_identity={**ident, "geometry_revision": 4},
        )
    layer.pop("geometry_revision")
    assert (
        layer_lookup.grid_from_cog(
            layer, "ndvi", "2026-07-01", 2, SimpleNamespace(to_gdal_path=lambda p: p)
        )["grid_identity"]
        is None
    )
