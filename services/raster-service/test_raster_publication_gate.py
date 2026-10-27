"""Publication gate: validate -> upload -> asset -> catalogue, then (and only then) readable.

Regression witnesses for the 2026-10-27 pixel-pipeline publication review:

* P2-PUB-1 — the in-memory layer and field index were registered *before* persistence,
  so a job that ended ``failed``/``publication_eligible=False`` was still served by the
  layer resolver and the COG grid reader.
* P2-PUB-2 — the writer's structural validation result (``validation.valid``) was only
  informational: an invalid COG was uploaded, persisted and published.
* P2-PUB-3 / ST-04 — a GIS catalogue (``raster_registry``) insert that returned False
  still yielded ``persisted=True`` (completed/eligible), and the asset row had already
  been written ``ready`` so DB readers resolved it.  A RuntimeError raised by the DB
  path was also mistaken for "event loop already running" and re-ran every insert.

These run the real orchestration, processor, writer, persistence adapter and resolver;
only the object-store upload and the async DB primitives are replaced.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import db_persist
import layer_lookup
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

pytestmark = pytest.mark.unit

TENANT = "00000000-0000-0000-0000-000000000001"
FIELD = "fld_pubgate"


def _req(raster_url: str | None = "file:///scene.tif", indicator: str = "ndvi", **extra):
    from raster_api_models import ProcessRequest

    return ProcessRequest(
        field_id=FIELD,
        tenant_id=TENANT,
        scene_id="scene_1",
        capture_datetime="2026-09-01",
        indicator=indicator,
        source_format="sentinel2_l2a",
        bands={"red": 1, "nir": 2},
        provider="cdse",
        raster_url=raster_url,
        precomputed_index=True,
        **extra,
    )


def _stub_ctx(tmp_path, *, persisted, cog_url="s3://bucket/fld_pubgate/ndvi_x.tif"):
    """Orchestration ctx with a stubbed processor that wrote a real readable COG."""
    from raster_api_models import JobStatus

    path = tmp_path / "ndvi.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=8,
        width=8,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(44, 15, 0.001, 0.001),
    ) as dst:
        dst.write(np.full((8, 8), 0.5, dtype="float32"), 1)
    jobs: dict = {}

    def persist(*_a, **_k):
        if isinstance(persisted, BaseException):
            raise persisted
        return persisted

    ctx = SimpleNamespace(
        _jobs=SimpleNamespace(get=jobs.get, set=jobs.__setitem__),
        _layers={},
        _field_layers={},
        JobStatus=JobStatus,
        logger=logging.getLogger(__name__),
        _process_precomputed_pixels=lambda *_: (
            {"valid_pixels": 64, "nodata_pixels": 0},
            [44, 14.992, 44.008, 15],
            10,
            {"cog_url": cog_url},
        ),
        _persist_raster_asset=persist,
    )
    store = SimpleNamespace(to_gdal_path=lambda _url: str(path), exists_locally=lambda _u: True)
    return ctx, jobs, store


def _resolve(ctx, store, monkeypatch, date="latest"):
    async def no_db_asset(*_a, **_k):
        return None

    monkeypatch.setattr(db_persist, "fetch_latest_asset", no_db_asset)
    return asyncio.run(
        layer_lookup.real_field_grid(
            FIELD,
            "ndvi",
            date,
            4,
            layers=ctx._layers,
            field_layers=ctx._field_layers,
            tenant_getter=lambda: TENANT,
            logger=logging.getLogger(__name__),
            object_store_module=store,
        )
    )


# ---------------------------------------------------------------- P2-PUB-1


@pytest.mark.parametrize(
    ("mode", "terminal"), [("required", "failed"), ("best_effort", "processed_unpublished")]
)
def test_unpersisted_result_is_not_resolvable_by_any_reader(tmp_path, monkeypatch, mode, terminal):
    monkeypatch.setenv("RASTER_PERSISTENCE_MODE", mode)
    from raster_job_orchestration import run_processing

    ctx, jobs, store = _stub_ctx(tmp_path, persisted=False)
    run_processing(ctx, "job_1", _req())
    job = jobs["job_1"]
    assert job["status"].value == terminal
    assert job["publication_eligible"] is False
    # No reader may observe an ineligible product: neither by layer id (tiles,
    # tilejson, layer metadata) nor through the field index (resolver, grid, dates).
    assert ctx._layers == {}, "ineligible layer registered in memory"
    assert ctx._field_layers.get(FIELD, []) == []
    assert (
        layer_lookup.find_field_layer(ctx._layers, ctx._field_layers, FIELD, "ndvi", "latest")
        is None
    )
    assert _resolve(ctx, store, monkeypatch) is None
    assert _resolve(ctx, store, monkeypatch, date="2026-09-01") is None
    # The result envelope must not advertise a tile endpoint that cannot be served.
    assert job["result"]["tile_url_template"] is None


def test_persistence_exception_leaves_nothing_readable(tmp_path, monkeypatch):
    monkeypatch.setenv("RASTER_PERSISTENCE_MODE", "required")
    from raster_job_orchestration import run_processing

    ctx, jobs, store = _stub_ctx(tmp_path, persisted=RuntimeError("db exploded"))
    run_processing(ctx, "job_1", _req())
    assert jobs["job_1"]["status"].value == "failed"
    assert ctx._layers == {}
    assert ctx._field_layers.get(FIELD, []) == []
    assert _resolve(ctx, store, monkeypatch) is None


def test_persisted_result_is_published_and_readable(tmp_path, monkeypatch):
    monkeypatch.setenv("RASTER_PERSISTENCE_MODE", "required")
    from raster_job_orchestration import run_processing

    ctx, jobs, store = _stub_ctx(tmp_path, persisted=True)
    run_processing(ctx, "job_1", _req())
    job = jobs["job_1"]
    assert job["status"].value == "completed"
    assert job["publication_eligible"] is True
    layer_id = job["result"]["layer_id"]
    assert ctx._field_layers[FIELD] == [layer_id]
    assert ctx._layers[layer_id]["cog_url"] == "s3://bucket/fld_pubgate/ndvi_x.tif"
    assert job["result"]["tile_url_template"] == f"/v1/tiles/{layer_id}/{{z}}/{{x}}/{{y}}.png"
    grid = _resolve(ctx, store, monkeypatch)
    assert grid is not None and grid["stats"]["mean"] == pytest.approx(0.5)


# ---------------------------------------------------------------- P2-PUB-2


def _write_ndvi_source(tmp_path):
    path = tmp_path / "provider_ndvi.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=32,
        width=32,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        nodata=-9999.0,
        transform=from_origin(44, 15, 0.0001, 0.0001),
    ) as dst:
        dst.write(np.full((32, 32), 0.5, dtype="float32"), 1)
    return path


def _write_rgba_source(tmp_path):
    path = tmp_path / "provider_truecolor.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=32,
        width=32,
        count=4,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(44, 15, 0.0001, 0.0001),
    ) as dst:
        dst.write(np.full((4, 32, 32), 200, dtype="uint8"))
    return path


def _real_ctx(tmp_path, uploads):
    import raster_processing_runtime

    ctx = raster_processing_runtime.make_processing_context(upload_dir=str(tmp_path))
    jobs: dict = {}
    ctx._jobs = SimpleNamespace(get=jobs.get, set=jobs.__setitem__)
    ctx._layers, ctx._field_layers = {}, {}

    def upload(path, key):
        uploads.append(key)
        return "s3://bucket/" + key

    ctx.object_store = SimpleNamespace(upload_cog=upload)
    ctx._persist_raster_asset = lambda *_a, **_k: True
    return ctx, jobs


@pytest.mark.parametrize(
    ("indicator", "writer"), [("ndvi", _write_ndvi_source), ("truecolor", _write_rgba_source)]
)
def test_structurally_invalid_cog_is_never_uploaded_or_published(
    tmp_path, monkeypatch, indicator, writer
):
    monkeypatch.setenv("RASTER_PERSISTENCE_MODE", "required")
    import cog_writer
    from raster_job_orchestration import run_processing

    monkeypatch.setattr(
        cog_writer, "validate_cog", lambda _p: {"valid": False, "reason": "not tiled"}
    )
    uploads: list = []
    ctx, jobs = _real_ctx(tmp_path, uploads)
    src = writer(tmp_path)
    run_processing(
        ctx, "job_1", _req(raster_url=str(src), indicator=indicator, raw_qa_required=False)
    )
    job = jobs["job_1"]
    assert uploads == [], "invalid COG was uploaded"
    assert job["status"].value == "failed"
    assert job["publication_eligible"] is False
    assert ctx._layers == {} and ctx._field_layers.get(FIELD, []) == []
    # The validator's verdict stays visible for diagnosis.
    assert job["result"]["stats"]["cog"]["validation"]["valid"] is False


@pytest.mark.parametrize(
    ("indicator", "writer"), [("ndvi", _write_ndvi_source), ("truecolor", _write_rgba_source)]
)
def test_valid_cog_still_flows_through_the_gate(tmp_path, monkeypatch, indicator, writer):
    monkeypatch.setenv("RASTER_PERSISTENCE_MODE", "required")
    from raster_job_orchestration import run_processing

    uploads: list = []
    ctx, jobs = _real_ctx(tmp_path, uploads)
    src = writer(tmp_path)
    run_processing(
        ctx, "job_1", _req(raster_url=str(src), indicator=indicator, raw_qa_required=False)
    )
    job = jobs["job_1"]
    assert job["result"]["stats"]["cog"]["validation"]["valid"] is True
    assert len(uploads) == 1
    assert job["status"].value == "completed"
    assert job["publication_eligible"] is True
    assert len(ctx._field_layers[FIELD]) == 1


def test_every_cog_upload_site_is_behind_the_validation_gate():
    """Raw and truecolor raw paths are not cheap to drive end-to-end; pin them by source."""
    import inspect

    import raster_pixel_processing

    src = inspect.getsource(raster_pixel_processing)
    uploads = src.count("ctx.object_store.upload_cog(")
    assert uploads == 4
    assert src.count("if _cog_publishable(cog_info):") == uploads
    assert 'if cog_info.get("written"):' not in src


def test_cog_publishable_requires_written_and_valid():
    from raster_pixel_processing import _cog_publishable

    assert _cog_publishable({"written": True, "validation": {"valid": True}}) is True
    assert _cog_publishable({"written": True, "validation": {"valid": False}}) is False
    assert _cog_publishable({"written": True, "validation": {"valid": None}}) is False
    assert _cog_publishable({"written": True}) is False
    assert _cog_publishable({"written": False, "validation": {"valid": True}}) is False


# ---------------------------------------------------------------- P2-PUB-3 / ST-04


def _patch_db(monkeypatch, *, asset=True, registry=True, promote=True):
    calls: list = []

    async def insert_asset(**kwargs):
        calls.append(("asset", kwargs.get("asset_status", "ready")))
        if isinstance(asset, BaseException):
            raise asset
        return asset

    async def insert_registry(**kwargs):
        calls.append(("registry", kwargs["cog_url"]))
        if isinstance(registry, BaseException):
            raise registry
        return registry

    async def set_status(**kwargs):
        calls.append(("status", kwargs["status"]))
        return promote if kwargs["status"] == "ready" else True

    monkeypatch.setattr(db_persist, "insert_raster_asset", insert_asset)
    monkeypatch.setattr(db_persist, "insert_raster_registry_entry", insert_registry)
    monkeypatch.setattr(db_persist, "set_raster_asset_status", set_status, raising=False)
    return calls


def _persist(cog_url="s3://bucket/fld_pubgate/ndvi_x.tif", stats=None):
    from raster_asset_persistence import persist_raster_asset

    return persist_raster_asset(
        _req(),
        cog_url,
        {"data_available_at": "2026-09-03T08:30:00+00:00"},
        [44, 15, 45, 16],
        stats or {"valid_pixels": 4, "nodata_pixels": 0},
        job_id="job_1",
    )


def test_catalogue_false_is_not_persisted_and_asset_is_never_ready(monkeypatch):
    calls = _patch_db(monkeypatch, registry=False)
    assert _persist() is False
    # Staged as pending (invisible to every ``asset_status='ready'`` reader) and
    # retired as failed: the row never became resolvable.
    assert calls[0] == ("asset", "pending")
    assert ("status", "ready") not in calls
    assert calls[-1] == ("status", "failed")


def test_catalogue_success_promotes_asset_after_registration(monkeypatch):
    calls = _patch_db(monkeypatch)
    assert _persist() is True
    assert calls == [
        ("asset", "pending"),
        ("registry", "s3://bucket/fld_pubgate/ndvi_x.tif"),
        ("status", "ready"),
    ]


def test_failed_promotion_is_not_persisted(monkeypatch):
    _patch_db(monkeypatch, promote=False)
    assert _persist() is False


def test_asset_insert_false_never_touches_catalogue(monkeypatch):
    calls = _patch_db(monkeypatch, asset=False)
    assert _persist() is False
    assert calls == [("asset", "pending")]


def test_local_file_cog_without_catalogue_is_written_ready(monkeypatch):
    """file:// COGs are deliberately not catalogued; the asset is the publication."""
    calls = _patch_db(monkeypatch)
    assert _persist("file:///data/uploads/ndvi_x.tif") is True
    assert calls == [("asset", "ready")]


def test_db_runtime_error_is_not_retried_as_event_loop_conflict(monkeypatch):
    calls = _patch_db(monkeypatch, registry=RuntimeError("registry down"))
    assert _persist() is False
    assert [c for c in calls if c[0] == "asset"] == [("asset", "pending")]
    assert [c for c in calls if c[0] == "registry"] == [
        ("registry", "s3://bucket/fld_pubgate/ndvi_x.tif")
    ]


def test_all_masked_product_is_never_catalogued_or_published(monkeypatch):
    """An all-masked COG is kept as a ``failed`` diagnostic row, never an observation.

    ``insert_raster_asset`` forces such a row ``failed``; cataloguing it anyway left a
    ``raster_registry`` entry that the GIS catalogue serves for a product that was never
    published (and, for file:// COGs, ``persisted=True`` registered it in memory).
    """
    masked = {"valid_pixels": 0, "nodata_pixels": 4}
    calls = _patch_db(monkeypatch)
    assert _persist(stats=masked) is False
    assert [c for c in calls if c[0] == "registry"] == []
    assert ("status", "ready") not in calls

    calls = _patch_db(monkeypatch)
    assert _persist("file:///data/uploads/ndvi_x.tif", stats=masked) is False
    assert calls == [("asset", "ready")]


def test_set_raster_asset_status_refuses_without_a_target(monkeypatch):
    """Guards that hold before any connection: no DB, unknown status, missing identity."""
    monkeypatch.setattr(db_persist, "DATABASE_URL", None)

    def status(**overrides):
        kwargs = {
            "tenant_id": TENANT,
            "product_identity_key": "pik",
            "cog_uri": "s3://bucket/x.tif",
            "status": "ready",
        } | overrides
        return asyncio.run(db_persist.set_raster_asset_status(**kwargs))

    assert status() is False  # no database: nothing promoted, nothing raised
    assert status(status="pending") is False
    assert status(status="stale") is False
    assert status(product_identity_key="") is False
    assert status(cog_uri="") is False


def test_set_raster_asset_status_sql_is_tenant_scoped_and_guarded():
    """The promotion SQL is pinned by source; its DB semantics are not simulated here.

    A stand-in connection would assert only what it was told (FAKE-CONNECTION-ENFORCES-
    NOTHING-01), so the statement itself is pinned: session-scoped tenant GUC on the
    same connection, and an UPDATE that can only move this product's own pending row.
    """
    import inspect

    src = inspect.getsource(db_persist.set_raster_asset_status)
    assert "SELECT set_config('app.current_tenant', $1, false)" in src
    assert src.index("set_config") < src.index("UPDATE raster_assets")
    assert '"UPDATE raster_assets SET asset_status = $1 "' in src
    assert (
        "\"WHERE product_identity_key = $2 AND cog_uri = $3 AND asset_status = 'pending'\"" in src
    )
