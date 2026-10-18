"""An empty CDSE outcome gets a cause only from catalogue evidence (probes P1–P8).

Injected clients, not a live provider: each probe pins which evidence may produce
which attribution, and that zero observable pixels alone never name a cause.
P7 (processing-baseline offset) is not a cause of an *empty* raster on this path
and has no probe here.
"""

from __future__ import annotations

import io
import json
import logging
import tarfile
from pathlib import Path

import cdse_client
import cdse_diagnostics
import cdse_native_product as native
import cdse_singleflight
import httpx
import numpy as np
import pytest
import raster_cdse_tile_runtime as runtime
import raster_settings
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

pytestmark = pytest.mark.unit
LOG = logging.getLogger(__name__)
OUTSIDE = {"type": "Polygon", "coordinates": [[[3, 3], [4, 3], [4, 4], [3, 4], [3, 3]]]}


def _tiff(values):
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=2,
            height=2,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(0, 2, 1, 1),
            nodata=float("nan"),
        ) as dst:
            dst.write(np.array(values, dtype="float32"), 1)
        return mem.read()


EMPTY = _tiff([[np.nan] * 2] * 2)
VALID = _tiff([[0.2] * 2] * 2)


def _scene(cloud):
    props = {"datetime": "2026-10-14T07:30:00Z"}
    if cloud is not None:
        props["eo:cloud_cover"] = cloud
    return {"id": f"S2-{cloud}", "properties": props}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(raster_settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("CDSE_DIAGNOSTIC_CATALOGUE_PROBE", "1")
    cdse_singleflight.cdse_tile_cache.clear()
    cdse_diagnostics._probe_cache.clear()
    yield
    for _expires, name in cdse_singleflight.cdse_tile_cache.values():
        Path(name).unlink(missing_ok=True)
    cdse_singleflight.cdse_tile_cache.clear()
    cdse_diagnostics._probe_cache.clear()


async def _run(
    monkeypatch, *, payload=EMPTY, catalogue=(), error=None, geometry=None, latest=False
):
    probes = []

    class Client:
        def process_index(self, **kwargs):
            if error:
                raise error
            return payload

        def search_scenes(self, **kwargs):
            if kwargs.get("max_cloud_pct") != 100.0:
                return []  # the cloud-filtered selection search finds nothing
            probes.append(kwargs)
            if isinstance(catalogue, Exception):
                raise catalogue
            return list(catalogue)

    monkeypatch.setattr(runtime._cdse, "get_client", Client)
    result = await runtime.ensure_field_cog(
        "field-one",
        "ndvi",
        "2026-10-14",
        "2026-10-01T00:00:00Z" if latest else "2026-10-14T00:00:00Z",
        "2026-10-14T23:59:59Z",
        [0, 0, 2, 2],
        geometry,
        bool(geometry),
        logger=LOG,
    )
    return result, probes


def _receipts(tmp_path):
    return [json.loads(p.read_text()) for p in (tmp_path / "cdse_diagnostics").glob("*.json")]


def _receipt(tmp_path):
    receipts = _receipts(tmp_path)
    assert len(receipts) == 1
    return receipts[0]


async def test_p1_no_acquisition_in_the_window(monkeypatch, tmp_path):
    result, probes = await _run(monkeypatch, catalogue=[])
    record = _receipt(tmp_path)
    assert result is None
    assert record["outcome"] == "empty_raster"
    assert record["response"]["catalogue_evidence"] == "no_acquisition"
    assert record["attribution"] == "no_acquisition_in_window"
    assert probes and probes[0]["max_retries"] == 0 and probes[0]["max_cloud_pct"] == 100.0


async def test_p2_acquisitions_exist_only_above_the_tile_cloud_limit(monkeypatch, tmp_path):
    await _run(monkeypatch, catalogue=[_scene(80.0), _scene(41.0)])
    record = _receipt(tmp_path)
    assert record["response"]["catalogue_evidence"] == "acquisitions_above_cloud_limit"
    assert record["attribution"] == "filtered_by_tile_cloud_cover"


async def test_p3_scene_within_limit_and_zero_pixels_names_no_cause(monkeypatch, tmp_path):
    """Cloud, SCL masking and no-data all read as NaN here; zeros alone decide nothing."""
    await _run(monkeypatch, catalogue=[_scene(80.0), _scene(12.0)])
    record = _receipt(tmp_path)
    assert record["response"]["catalogue_evidence"] == "acquisitions_within_cloud_limit"
    assert record["attribution"] == "unknown"


async def test_p3_unknown_cloud_cover_is_not_read_as_filtered(monkeypatch, tmp_path):
    await _run(monkeypatch, catalogue=[_scene(None), _scene(90.0)])
    record = _receipt(tmp_path)
    assert record["response"]["catalogue_evidence"] == "acquisitions_cloud_cover_unknown"
    assert record["attribution"] == "unknown"


async def test_p4_polygon_mask_evidence_outranks_the_catalogue(monkeypatch, tmp_path):
    await _run(monkeypatch, payload=VALID, geometry=OUTSIDE, catalogue=[])
    record = _receipt(tmp_path)
    assert record["response"]["before_mask"]["observable_pixels"] == 4
    assert record["attribution"] == "polygon_mask_removed_observations"


@pytest.mark.parametrize(
    "failure",
    [cdse_client.CdseCatalogError("timeout"), cdse_client.CdseCatalogError("http_error", 503)],
)
async def test_p5_catalogue_outage_is_unavailable_never_no_acquisition(
    monkeypatch, tmp_path, failure
):
    await _run(monkeypatch, catalogue=failure)
    record = _receipt(tmp_path)
    assert record["response"]["catalogue_evidence"] == "catalogue_unavailable"
    assert record["attribution"] == "unknown"


async def test_p5_probe_is_off_by_default_and_then_asks_nothing(monkeypatch, tmp_path):
    monkeypatch.delenv("CDSE_DIAGNOSTIC_CATALOGUE_PROBE")
    _result, probes = await _run(monkeypatch, catalogue=[])
    record = _receipt(tmp_path)
    assert probes == []
    assert record["response"]["catalogue_evidence"] == "not_available"
    assert record["attribution"] == "unknown"


async def test_p6_provider_status_keeps_its_own_attribution_and_skips_the_probe(
    monkeypatch, tmp_path
):
    request = httpx.Request("POST", "https://cdse.invalid/process")
    error = httpx.HTTPStatusError(
        "429", request=request, response=httpx.Response(429, request=request)
    )
    _result, probes = await _run(monkeypatch, error=error, catalogue=[])
    record = _receipt(tmp_path)
    assert probes == []
    assert record["attribution"] == "rate_limited"
    assert record["response"]["catalogue_evidence"] == "not_available"


async def test_p8_valid_raster_writes_no_receipt_and_asks_nothing(monkeypatch, tmp_path):
    result, probes = await _run(monkeypatch, payload=VALID, catalogue=[])
    assert result is not None
    assert probes == []
    assert _receipts(tmp_path) == []


async def test_latest_window_without_eligible_scene_uses_the_same_evidence(monkeypatch, tmp_path):
    await _run(monkeypatch, latest=True, catalogue=[_scene(95.0)])
    record = _receipt(tmp_path)
    assert record["outcome"] == "no_selected_scene"
    assert record["attribution"] == "filtered_by_tile_cloud_cover"


async def test_repeated_failures_reuse_one_probe(monkeypatch, tmp_path):
    _result, first = await _run(monkeypatch, catalogue=[])
    _result, second = await _run(monkeypatch, catalogue=[])
    assert len(first) == 1 and second == []


def test_probe_answers_expire_and_the_cache_is_bounded():
    key = cdse_diagnostics.probe_key([0, 0, 1, 1], None, "a", "b", 40.0)
    cdse_diagnostics.remember_probe(key, "no_acquisition", now=1000.0)
    ttl = cdse_diagnostics.CATALOGUE_PROBE_TTL_SECONDS
    assert cdse_diagnostics.cached_probe(key, now=1000.0 + ttl - 1) == "no_acquisition"
    assert cdse_diagnostics.cached_probe(key, now=1000.0 + ttl + 1) is None
    for i in range(cdse_diagnostics.CATALOGUE_PROBE_MAX_ENTRIES + 20):
        other = cdse_diagnostics.probe_key([0, 0, 1, i + 1], None, "a", "b", 40.0)
        cdse_diagnostics.remember_probe(other, "no_acquisition", now=float(i))
    assert len(cdse_diagnostics._probe_cache) == cdse_diagnostics.CATALOGUE_PROBE_MAX_ENTRIES
    assert cdse_diagnostics.remember_probe(key, "clouds, surely") == "not_available"


@pytest.mark.parametrize(
    "scenes,limit,expected",
    [
        ([], 40.0, "no_acquisition"),
        ([_scene(40.0)], 40.0, "acquisitions_within_cloud_limit"),
        ([_scene(40.01)], 40.0, "acquisitions_above_cloud_limit"),
        ([_scene(float("nan"))], 40.0, "acquisitions_cloud_cover_unknown"),
        ([_scene("12")], 40.0, "acquisitions_cloud_cover_unknown"),
        (None, 40.0, "catalogue_unavailable"),
    ],
)
def test_catalogue_evidence_classification(scenes, limit, expected):
    assert cdse_diagnostics.catalogue_evidence(scenes, limit) == expected


def test_receipt_rejects_unlisted_catalogue_evidence():
    record = cdse_diagnostics.failure_receipt(
        tenant="t",
        field_id="f",
        index="ndvi",
        date_from=None,
        date_to=None,
        bbox=None,
        geometry=None,
        max_cloud_pct=40.0,
        outcome="empty_raster",
        catalogue="clouds, surely",
    )
    assert record["response"]["catalogue_evidence"] == "not_available"
    assert record["attribution"] == "unknown"


def test_catalogue_evidence_never_names_a_cause_for_other_outcomes():
    record = cdse_diagnostics.failure_receipt(
        tenant="t",
        field_id="f",
        index="ndvi",
        date_from=None,
        date_to=None,
        bbox=None,
        geometry=None,
        max_cloud_pct=40.0,
        outcome="mask_failed",
        catalogue="no_acquisition",
    )
    assert record["attribution"] == "unknown"


def _archive(tiles):
    metadata = json.dumps({"schema": native.SCHEMA, "tiles": tiles}).encode()
    mem = io.BytesIO()
    with tarfile.open(fileobj=mem, mode="w") as archive:
        for name, content in (("default.tif", VALID), ("userdata.json", metadata)):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return mem.getvalue()


def test_native_product_with_no_contributing_tile_has_its_own_reason():
    """Backfill asks CDSE for an Element84-chosen day; zero tiles is CDSE's answer, not junk."""
    with pytest.raises(native.CdseNoContributingScene, match="no_contributing_scene"):
        native.decode_response(_archive([]), "script")
    assert issubclass(native.CdseNoContributingScene, ValueError)  # callers still fail closed


@pytest.mark.parametrize("tiles", [None, "x", [{"id": str(i), "date": "x"} for i in range(257)]])
def test_malformed_native_tiles_stay_invalid_not_no_scene(tiles):
    with pytest.raises(ValueError) as caught:
        native.decode_response(_archive(tiles), "script")
    assert not isinstance(caught.value, native.CdseNoContributingScene)
