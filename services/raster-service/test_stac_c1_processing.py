"""Real TIFF/VRT calibration and runtime dispatch witnesses on synthetic C1 scenes.

Provider captures are separate evidence. These tests substitute only catalogue
I/O and the processing scheduler/persistence boundary, not GDAL or calibration.
"""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path

import numpy as np
import pytest
import radiometry_containment as rc
import rasterio
import stac_c1_processing as c1
import stac_vrt
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("coefficient", ["scale", "offset"])
def test_oversized_calibration_is_contained(scene, coefficient):
    data, _, _ = scene
    data["radiometry_context"]["assets"]["red"]["raster:bands"][0][coefficient] = 10**400
    with pytest.raises(rc.RadiometryUnresolved):
        c1.validate_c1_scene(data, entry_point="test")


@pytest.mark.parametrize("coefficient", ["scale", "offset"])
def test_vrt_oversized_calibration_is_an_input_error(scene, tmp_path, coefficient):
    data, _, _ = scene
    data["radiometry_context"]["assets"]["red"]["raster:bands"][0][coefficient] = 10**400
    with pytest.raises(ValueError, match="finite explicit"):
        stac_vrt.build_band_vrt(
            data["bands_urls"], str(tmp_path), stac_item=data["radiometry_context"]
        )
    assert not list(tmp_path.glob("stac_stack_*"))


def test_nonintersecting_clip_is_contained_and_no_processing_runs(scene, tmp_path):
    data, _, _ = scene
    clip = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    with pytest.raises(rc.RadiometryUnresolved):
        c1.process_c1_scene(
            data,
            "ndvi",
            "field",
            "tenant",
            None,
            clip,
            True,
            "job",
            run_processing=lambda *_: pytest.fail("nonintersecting scene was processed"),
            out_dir=str(tmp_path),
            entry_point="test",
        )
    assert not list(tmp_path.glob("stac_c1_*"))


def test_multiresolution_vrt_matches_analytic_nearest_samples_and_calibration(tmp_path):
    """Independent array oracle: 20 m pixels repeat 2x2 on the fixed 10 m grid."""
    arrays = {
        "red": np.arange(16, dtype="uint16").reshape(4, 4) * 100 + 2000,
        "nir": np.array([[4000, 6000], [8000, 10000]], dtype="uint16"),
        "scl": np.array([[4, 9], [6, 11]], dtype="uint16"),
    }
    arrays["red"][0, 0] = 0
    paths = {}
    for name, data in arrays.items():
        path = tmp_path / f"analytic-{name}.tif"
        resolution = 10 if name == "red" else 20
        with (
            rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True),
            rasterio.open(
                path,
                "w",
                driver="GTiff",
                width=data.shape[1],
                height=data.shape[0],
                count=1,
                dtype="uint16",
                crs="EPSG:32638",
                nodata=0,
                transform=from_origin(500000, 1800000, resolution, resolution),
            ) as dst,
        ):
            dst.write(data, 1)
            dst.scales, dst.offsets = ((1,), (0,)) if name == "scl" else ((0.0001,), (-0.1,))
            if name == "nir":
                dst.write_mask(np.array([[255, 255], [0, 255]], dtype="uint8"))
        paths[name] = str(path)
    path, mapping = stac_vrt.build_band_vrt(paths, str(tmp_path))
    expected_nir = arrays["nir"].repeat(2, axis=0).repeat(2, axis=1) * 0.0001 - 0.1
    expected_red = arrays["red"] * 0.0001 - 0.1
    expected_valid = np.ones((4, 4), dtype=bool)
    expected_valid[0, 0] = False
    expected_valid[2:, :2] = False
    with rasterio.open(path) as src:
        assert (src.width, src.height) == (4, 4)
        assert src.transform == from_origin(500000, 1800000, 10, 10)
        red = (
            src.read(mapping["red"], masked=True) * src.scales[mapping["red"] - 1]
            + src.offsets[mapping["red"] - 1]
        )
        nir = (
            src.read(mapping["nir"], masked=True) * src.scales[mapping["nir"] - 1]
            + src.offsets[mapping["nir"] - 1]
        )
        ndvi = (nir - red) / (nir + red)
        np.testing.assert_array_equal(~np.ma.getmaskarray(ndvi), expected_valid)
        np.testing.assert_allclose(
            ndvi.compressed(),
            ((expected_nir - expected_red) / (expected_nir + expected_red))[expected_valid],
            rtol=1e-6,
            atol=1e-7,
        )
        np.testing.assert_array_equal(
            src.read(mapping["scl"]), arrays["scl"].repeat(2, axis=0).repeat(2, axis=1)
        )


@pytest.fixture
def scene(tmp_path, monkeypatch):
    identity = "S2A_T38QND_20261015T073428_L2A"
    captured = "2026-10-15T07:34:28Z"
    assets, paths = {}, {}
    aliases = {"swir1": "swir16", "swir2": "swir22", "rededge": "rededge1"}
    for name, band in c1.BANDS.items():
        href = f"https://{c1.C1_HOST}/{c1.C1_COLLECTION}/38/Q/ND/2026/10/{identity}/{band}.tif"
        path = tmp_path / f"{name}.tif"
        scale, offset = (1, 0) if name == "scl" else (0.0001, -0.1)
        value = {"red": 2000, "nir": 4000, "blue": 1500, "scl": 4}.get(name, 3000)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=8,
            height=8,
            count=1,
            dtype="uint16",
            crs="EPSG:32638",
            nodata=0,
            transform=from_origin(500000, 1800000, 10, 10),
        ) as dst:
            dst.write(np.full((8, 8), value, dtype="uint16"), 1)
            dst.scales, dst.offsets = (scale,), (offset,)
        paths[href] = str(path)
        assets[aliases.get(name, name)] = {
            "href": href,
            "roles": ["data"] if name == "scl" else ["data", "reflectance"],
            "raster:bands": [
                {"scale": scale, "offset": offset, "nodata": 0, "data_type": "uint16"}
            ],
        }
    context = {
        "id": identity,
        "collection": c1.C1_COLLECTION,
        "properties": {"s2:processing_baseline": "05.11", "datetime": captured},
        "assets": assets,
    }
    scene = {
        "item_id": identity,
        "datetime": captured,
        "bands_urls": c1.stac_search.band_urls_from_assets(assets),
        "radiometry_context": context,
    }
    monkeypatch.setattr(stac_vrt, "_as_gdal_source", lambda href: paths[href])
    bounds = transform_bounds("EPSG:32638", "EPSG:4326", 500010, 1799930, 500070, 1799990)
    x1, y1, x2, y2 = bounds
    clip = {"type": "Polygon", "coordinates": [[[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]]}
    return scene, clip, paths


def test_c1_calibration_reaches_processing_once_and_bundle_is_removed(scene, tmp_path):
    data, clip, _ = scene
    calls = []

    def process(jid, req):
        with rasterio.open(req.raster_url) as src:
            red = (
                src.read(req.bands.red, masked=True) * src.scales[req.bands.red - 1]
                + src.offsets[req.bands.red - 1]
            )
            nir = (
                src.read(req.bands.nir, masked=True) * src.scales[req.bands.nir - 1]
                + src.offsets[req.bands.nir - 1]
            )
            assert float(((nir - red) / (nir + red)).mean()) == pytest.approx(0.5)
            assert src.width <= 8 and src.height <= 8
            assert set(np.unique(src.read(req.bands.scl))) == {4}
        assert req.tenant_id == "tenant" and req.field_id == "field"
        assert req.raw_qa_required and req.apply_cloud_mask
        assert req.reflectance_scale is None and req.reflectance_offset is None
        calls.append(req.raster_url)

    c1.process_c1_scene(
        data,
        "evi",
        "field",
        "tenant",
        3,
        clip,
        True,
        "job",
        run_processing=process,
        out_dir=str(tmp_path),
        entry_point="test",
    )
    assert len(calls) == 1 and not Path(calls[0]).exists()
    assert not list(tmp_path.glob("stac_c1_*"))


@pytest.mark.parametrize(
    "defect", ["legacy", "href", "item", "time", "baseline", "boa", "missing_band", "scale", "role"]
)
def test_invalid_provider_contract_stays_contained_before_any_raster_open(
    scene, monkeypatch, defect
):
    data, _, _ = scene
    data = copy.deepcopy(data)
    context = data["radiometry_context"]
    if defect == "legacy":
        context["collection"] = "sentinel-2-l2a"
    elif defect == "href":
        data["bands_urls"]["red"] = "https://evil.test/B04.tif"
    elif defect == "item":
        context["id"] = "another"
    elif defect == "time":
        data["datetime"] = "2020-01-01T00:00:00Z"
    elif defect == "baseline":
        context["properties"]["s2:processing_baseline"] = "05.09"
    elif defect == "boa":
        context["properties"]["earthsearch:boa_offset_applied"] = True
    elif defect == "missing_band":
        del data["bands_urls"]["scl"]
    elif defect == "scale":
        context["assets"]["red"]["raster:bands"][0]["scale"] = float("nan")
    elif defect == "role":
        context["assets"]["red"]["roles"] = ["visual"]
    with pytest.raises(rc.RadiometryUnresolved):
        c1.validate_c1_scene(data, entry_point="test")


def test_c1_requires_tiff_stac_agreement_and_removes_partial_bundle(scene, tmp_path):
    data, clip, paths = scene
    with rasterio.open(paths[data["bands_urls"]["nir"]], "r+") as src:
        src.offsets = (0.0,)
    with pytest.raises(rc.RadiometryUnresolved):
        c1.process_c1_scene(
            data,
            "ndvi",
            "field",
            "tenant",
            None,
            clip,
            True,
            "job",
            run_processing=lambda *_: pytest.fail("processing before validation"),
            out_dir=str(tmp_path),
            entry_point="test",
        )
    assert not list(tmp_path.glob("stac_c1_*"))


@pytest.mark.parametrize(
    "field,tenant,clip_present,mask",
    [
        ("field", "", True, True),
        ("", "tenant", True, True),
        ("field", "tenant", False, True),
        ("field", "tenant", True, False),
    ],
)
def test_c1_keeps_tenant_clip_and_mask_preconditions(
    scene, tmp_path, field, tenant, clip_present, mask
):
    data, clip, _ = scene
    with pytest.raises(rc.RadiometryUnresolved):
        c1.process_c1_scene(
            data,
            "ndvi",
            field,
            tenant,
            None,
            clip if clip_present else None,
            mask,
            "job",
            run_processing=lambda *_: pytest.fail("unsafe execution"),
            out_dir=str(tmp_path),
            entry_point="test",
        )


def test_clip_pixel_budget_fails_before_creating_a_bundle(scene, tmp_path):
    data, clip, _ = scene
    with pytest.raises(ValueError, match="pixel budget"):
        stac_vrt.build_band_vrt(
            data["bands_urls"],
            str(tmp_path),
            stac_item=data["radiometry_context"],
            clip_geometry=clip,
            max_pixels=1,
        )
    assert not list(tmp_path.glob("stac_stack_*"))


def test_worker_dispatches_supported_c1_into_existing_processing_core(scene, tmp_path, monkeypatch):
    import backfill_scan_worker as worker

    data, clip, _ = scene
    calls = []
    monkeypatch.setattr(worker.raster_settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        worker.raster_processing_runtime,
        "run_processing",
        lambda jid, req: calls.append((jid, req)),
    )
    monkeypatch.setattr(worker, "_outcome_from_job", lambda jid: worker.SceneOutcome(True))
    outcome = worker._process_scene_index(data, "evi", "field", "tenant", 3, clip, True, "job")
    assert outcome.ok and len(calls) == 1
    assert calls[0][1].scene_id == data["item_id"]


def test_direct_route_resolves_catalogue_then_schedules_supported_c1(scene, tmp_path, monkeypatch):
    from fastapi import BackgroundTasks
    from raster_api_models import ProcessFromStacRequest
    from routers import fields

    data, clip, _ = scene
    calls = []
    stored = {}

    async def owner(_):
        return None

    async def query(payload):
        assert payload["collections"] == [c1.C1_COLLECTION] and payload["ids"] == [data["item_id"]]
        return {"features": [data["radiometry_context"]]}

    monkeypatch.setattr(fields, "_require_service_token", lambda _: None)
    monkeypatch.setattr(fields, "_require_field_tenant", owner)
    monkeypatch.setattr(fields, "_authenticated_tenant", lambda _: "tenant")
    monkeypatch.setattr(c1.stac_search, "stac_query", query)
    monkeypatch.setattr(fields, "_upload_dir", lambda: str(tmp_path))
    monkeypatch.setattr(fields, "_run_processing", lambda jid, req: calls.append(req))
    monkeypatch.setattr(fields._jobs, "set", lambda jid, value: stored.__setitem__(jid, value))
    tasks = BackgroundTasks()
    req = ProcessFromStacRequest(
        scene_id=data["item_id"], band_hrefs=data["bands_urls"], clip_polygon_geojson=clip
    )
    result = asyncio.run(fields.process_from_stac("field", req, tasks, x_agent_token="token"))
    assert result["status"] == "pending" and len(tasks.tasks) == 1
    task = tasks.tasks[0]
    task.func(*task.args, **task.kwargs)
    assert len(calls) == 1 and calls[0].raw_qa_required


@pytest.mark.parametrize("defect", ["requested_asset", "returned_item", "capture_time", "tenant"])
def test_direct_route_rejects_unbound_or_unauthenticated_requests_without_jobs(
    scene, monkeypatch, defect
):
    from fastapi import BackgroundTasks, HTTPException
    from raster_api_models import ProcessFromStacRequest
    from routers import fields

    data, clip, _ = scene

    async def owner(_):
        return None

    async def query(_):
        return {"features": [data["radiometry_context"]]}

    monkeypatch.setattr(fields, "_require_service_token", lambda _: None)
    monkeypatch.setattr(fields, "_require_field_tenant", owner)
    monkeypatch.setattr(
        fields, "_authenticated_tenant", lambda _: None if defect == "tenant" else "tenant"
    )
    monkeypatch.setattr(c1.stac_search, "stac_query", query)
    monkeypatch.setattr(
        fields._jobs, "set", lambda *_: pytest.fail("rejected request created a job")
    )
    req = ProcessFromStacRequest(
        scene_id=data["item_id"], band_hrefs=data["bands_urls"], clip_polygon_geojson=clip
    )
    if defect == "requested_asset":
        req.band_hrefs["red"] = "https://evil.test/raw.tif"
    elif defect == "returned_item":
        req.scene_id = "S2B_T38PNC_20261015T073428_L2A"
    elif defect == "capture_time":
        req.capture_datetime = "2020-01-01T00:00:00Z"
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            fields.process_from_stac("field", req, BackgroundTasks(), x_agent_token="token")
        )
    assert error.value.status_code == (403 if defect == "tenant" else 422)


def test_captured_provider_windows_replay_through_real_qa_and_cog(tmp_path, monkeypatch):
    """Offline replay of 2026-10-16 live captures, not a new network/live test."""
    import hashlib
    import json
    from types import SimpleNamespace

    import raster_pixel_processing
    import raster_processing_runtime
    from rasterio.mask import mask
    from rasterio.warp import transform_geom

    root = (
        Path(__file__).resolve().parents[2]
        / "certification/evidence/chatgpt_closure_nine_20261016/radiometry/provider"
    )
    item = json.loads((root / "selected-item.json").read_text())
    receipt = json.loads((root / "provider-pixel-receipt.json").read_text())
    paths = {}
    for name, band in receipt["bands"].items():
        with np.load(root / (name + "-window.npz")) as sample:
            data, valid = sample["data"], ~sample["mask"]
        assert hashlib.sha256(data.tobytes()).hexdigest() == band["array_sha256"]
        path = tmp_path / (name + ".tif")
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=data.shape[1],
            height=data.shape[0],
            count=1,
            dtype=data.dtype,
            nodata=band["nodata"],
            crs=band["crs"],
            transform=rasterio.Affine(*band["transform"][:6]),
        ) as dst:
            dst.write(data, 1)
            dst.write_mask(valid.astype("uint8") * 255)
            dst.scales, dst.offsets = band["tiff_scales"], band["tiff_offsets"]
        paths[band["href"]] = str(path)
    with rasterio.open(paths[item["assets"]["red"]["href"]]) as src:
        b = src.bounds
        bounds = transform_bounds(
            src.crs, "EPSG:4326", b.left + 20, b.bottom + 20, b.right - 20, b.top - 20
        )
    x1, y1, x2, y2 = bounds
    clip = {"type": "Polygon", "coordinates": [[[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]]}
    context = c1.stac_search.radiometry_context_from_item(item)
    data = {
        "item_id": item["id"],
        "datetime": item["properties"]["datetime"],
        "bands_urls": c1.stac_search.band_urls_from_assets(item["assets"]),
        "radiometry_context": context,
    }
    reflectance = {}
    for key in ("red", "nir", "blue"):
        with rasterio.open(paths[item["assets"][key]["href"]]) as src:
            a, _ = mask(
                src,
                [transform_geom("EPSG:4326", src.crs, clip)],
                crop=True,
                filled=False,
                indexes=[1],
            )
            samples = np.ma.filled(a[0].astype("float32"), np.nan)
            band = item["assets"][key]["raster:bands"][0]
            reflectance[key] = samples * band["scale"] + band["offset"]
    # Independent direct-sample EVI equation (no implementation formula/helper).
    red, nir, blue = (reflectance[k] for k in ("red", "nir", "blue"))
    expected = 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)
    ctx = raster_processing_runtime.make_processing_context(upload_dir=str(tmp_path))
    ctx.object_store = SimpleNamespace(upload_cog=lambda path, key: "file://" + path)
    monkeypatch.setattr(stac_vrt, "_as_gdal_source", lambda href: paths[href])
    results = []

    def process(jid, req):
        stats, _, _, meta = raster_pixel_processing.process_pixels(ctx, req, jid)
        assert stats["validated_raster_product"]["reflectance_normalized"]
        assert stats["cloud_mask_sources"] == ["SCL"]
        assert stats["cog"]["written"]
        with rasterio.open(meta["cog_url"].removeprefix("file://")) as src:
            actual = src.read(1, masked=True).filled(np.nan)
        np.testing.assert_allclose(actual, expected, rtol=2e-5, atol=1e-7, equal_nan=True)
        results.append(stats)

    c1.process_c1_scene(
        data,
        "evi",
        "public-provider-proof",
        "isolated-local-proof",
        None,
        clip,
        True,
        "provider-replay",
        run_processing=process,
        out_dir=str(tmp_path),
        entry_point="captured_provider_replay",
    )
    assert len(results) == 1
    assert results[0]["valid_pixels"] == 3600


def test_sync_backfill_dispatches_supported_c1_into_existing_processing_core(
    scene, tmp_path, monkeypatch
):
    from fastapi import BackgroundTasks
    from raster_api_models import HistoricalBackfillRequest
    from routers import fields

    data, clip, _ = scene
    calls, stored = [], {}

    async def owner(*args):
        return None

    async def search(*args, **kwargs):
        return {"items": [data], "count": 1}

    monkeypatch.setattr(fields, "_require_service_token", lambda _: None)
    monkeypatch.setattr(fields, "_require_field_tenant", owner)
    monkeypatch.setattr(fields, "_async_backfill_enabled", lambda: False)
    monkeypatch.setattr(fields, "_authenticated_tenant", lambda _: "tenant")
    monkeypatch.setattr(fields, "_stac_search", search)
    monkeypatch.setattr(fields, "_select_backfill_scenes_by_policy", lambda items, **kw: items)
    monkeypatch.setattr(fields, "_upload_dir", lambda: str(tmp_path))
    monkeypatch.setattr(fields, "_run_processing", lambda jid, req: calls.append(req))
    monkeypatch.setattr(fields._jobs, "set", lambda jid, job: stored.__setitem__(jid, job))
    monkeypatch.setattr(fields._jobs, "get", lambda jid: stored.get(jid))
    tasks = BackgroundTasks()
    req = HistoricalBackfillRequest(
        indices=["evi"],
        from_date="2026-10-01",
        to_date="2026-10-16",
        preset="custom",
        clip_polygon_geojson=clip,
    )
    asyncio.run(fields.field_historical_backfill("field", req, tasks, x_agent_token="token"))
    jobs = [task for task in tasks.tasks if task.func.__name__ == "_run_scene_job"]
    assert len(jobs) == 1
    for job in jobs:
        job.func(*job.args, **job.kwargs)
    assert len(calls) == 1 and calls[0].scene_id == data["item_id"]
    assert calls[0].tenant_id == "tenant" and calls[0].raw_qa_required
