import json
import os
import sys

import httpx
import numpy as np
import pytest

from tools.eo_acceptance.stac import Limiter, compare, crawl


def test_runner_retains_partial_evidence_and_redacts_http_error(tmp_path, monkeypatch):
    from tools.eo_acceptance import run, stac

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "old": "https://old.example/v1",
                "new": "https://new.example/v1",
                "queries": [{"name": "fixed-aoi", "payload": {}}],
            }
        )
    )
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        sys, "argv", ["run", "stac", "--manifest", str(manifest), "--output", str(output)]
    )
    calls = []

    def fake_crawl(*args):
        calls.append(True)
        if len(calls) == 1:
            return {}, {"seconds": 0.1, "requests": 1, "429": 0, "pages": 1}
        request = httpx.Request("POST", "https://example.com/?token=redaction_marker")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("redaction_marker", request=request, response=response)

    monkeypatch.setattr(stac, "crawl", fake_crawl)
    assert run.main() == 1
    report = json.loads(output.read_text())
    assert report["status"] == "ERROR" and report["upstream_status"] == 401
    assert len(report["partial_samples"]["fixed-aoi"]["old"]) == 1
    assert report["partial_samples"]["fixed-aoi"]["new"] == []
    assert "redaction_marker" not in output.read_text()


class Clock:
    now = 0.0

    def clock(self):
        return self.now

    def sleep(self, delay):
        self.now += delay


@pytest.mark.parametrize("authenticated,limit", [(False, 60), (True, 240)])
def test_both_rate_windows(authenticated, limit):
    clock = Clock()
    limiter = Limiter(authenticated, clock.clock, clock.sleep)
    times = []
    for _ in range(limit + 1):
        limiter.acquire()
        times.append(clock.now)
    assert times[10] >= 1
    assert times[-1] >= 60
    assert all(sum(t <= x < t + 1 for x in times) <= 10 for t in times)
    assert all(sum(t <= x < t + 60 for x in times) <= limit for t in times)


def feature(identity):
    return {
        "id": identity,
        "collection": "s2",
        "properties": {"datetime": "2026-10-01"},
        "assets": {},
    }


@pytest.mark.parametrize("method,merge", [("GET", False), ("POST", False), ("POST", True)])
def test_complete_pagination(method, merge):
    requests = []

    def transport(request):
        requests.append(request)
        links = (
            []
            if len(requests) > 1
            else [
                dict(
                    rel="next",
                    href="/v1/search?page=2",
                    method=method,
                    body={"token": "two"},
                    merge=merge,
                )
            ]
        )
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [feature(str(len(requests)))],
                "links": links,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        items, metrics = crawl(client, "https://example.com/v1", {"limit": 1}, Limiter())
    assert len(items) == 2 and metrics["pages"] == 2
    if method == "POST":
        assert json.loads(requests[1].content) == (
            {"limit": 1, "token": "two"} if merge else {"token": "two"}
        )


@pytest.mark.parametrize("failure", ["duplicate", "cycle", "cross_origin", "budget", "malformed"])
def test_incomplete_results_fail(failure):
    calls = []

    def transport(request):
        calls.append(request)
        link = {"rel": "next", "href": "/v1/search", "method": "POST", "body": {"page": len(calls)}}
        if failure == "cycle":
            link["body"] = {}
        if failure == "cross_origin":
            link["href"] = "https://other.com/search"
        data = {
            "type": "FeatureCollection",
            "features": [feature("same" if failure == "duplicate" else str(len(calls)))],
            "links": [link],
        }
        return httpx.Response(200, json={} if failure == "malformed" else data)

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(ValueError):
            crawl(client, "https://example.com/v1", {}, Limiter(), max_pages=3)


def test_429_is_counted_and_retried():
    count = []
    clock = Clock()

    def transport(request):
        count.append(request)
        if len(count) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"type": "FeatureCollection", "features": [feature("one")]})

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        _, metrics = crawl(
            client, "https://example.com/v1", {}, Limiter(False, clock.clock, clock.sleep)
        )
    assert metrics["429"] == 1 and metrics["requests"] == 2 and clock.now == 2


def test_empty_or_changed_catalogues_do_not_pass():
    assert not compare({}, {})["correctness_pass"]
    assert not compare({("s2", "1"): feature("1")}, {})["correctness_pass"]
    old = feature("1")
    new = feature("1")
    new["assets"] = {"B04": {"raster:bands": [{"offset": -0.1}]}}
    assert not compare({("s2", "1"): old}, {("s2", "1"): new})["correctness_pass"]


def test_equivalent_datetime_precision_and_role_order_are_not_differences():
    old, new = feature("one"), feature("one")
    old["properties"]["datetime"] = "2025-01-01T07:23:11.024Z"
    new["properties"]["datetime"] = "2025-01-01T07:23:11.024000Z"
    old["assets"] = {"B04": {"roles": ["data", "reflectance"]}}
    new["assets"] = {"B04": {"roles": ["reflectance", "data"]}}
    assert compare({("s2", "one"): old}, {("s2", "one"): new})["correctness_pass"]


def test_missing_next_link_cannot_prove_completeness():
    response = {"type": "FeatureCollection", "features": [feature("one")], "numberMatched": 2}
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response))
    ) as client:
        with pytest.raises(ValueError, match="missing pages"):
            crawl(client, "https://example.com/v1", {}, Limiter())


@pytest.mark.parametrize("offset", [0.0, -0.1])
def test_real_vrt_against_independent_oracle(tmp_path, offset):
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import transform_geom

    from tools.eo_acceptance.raster import compare_window

    paths = {}
    for name in ("red", "nir", "scl"):
        scl = name == "scl"
        size, resolution = (16, 20) if scl else (32, 10)
        data = np.full((size, size), 4 if scl else 3000, dtype="uint16")
        if not scl:
            data += np.arange(size, dtype="uint16")[None, :] * (40 if name == "nir" else 15)
            if name == "nir":
                data += 2000
            data[4, 4] = 0
            data[8, 8] = 65535
        else:
            data[2:4, 2:4] = 9
            data[5:7, 5:7] = 3
        path = tmp_path / f"{name}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=size,
            height=size,
            count=1,
            dtype="uint16",
            crs="EPSG:32638",
            nodata=0,
            transform=from_origin(400000, 1772000, resolution, resolution),
        ) as dst:
            dst.write(data, 1)
            dst.scales = (1 if scl else 0.0001,)
            dst.offsets = (0 if scl else offset,)
            if name == "nir":
                internal_mask = np.full((size, size), 255, dtype="uint8")
                internal_mask[12:14, 8:12] = 0
                dst.write_mask(internal_mask)
        paths[name] = str(path)
    poly = {
        "type": "Polygon",
        "coordinates": [
            [
                [400020, 1771980],
                [400280, 1771980],
                [400280, 1771740],
                [400020, 1771740],
                [400020, 1771980],
            ]
        ],
    }
    geometry = transform_geom("EPSG:32638", "EPSG:4326", poly)
    result = compare_window(paths, geometry, tmp_path / "vrt")
    assert result["mask_equal"] and result["max_error"] <= 1e-5
    assert abs(result["mean_ndvi_minus_ndvi_of_means"]) > 1e-6
    from tools.eo_acceptance.raster import benchmark_windows

    shifted = json.loads(json.dumps(poly))
    for point in shifted["coordinates"][0]:
        point[0] += 20
    second_geometry = transform_geom("EPSG:32638", "EPSG:4326", shifted)
    benchmark = benchmark_windows(paths, [geometry, second_geometry], 20)
    assert benchmark["correctness_pass"]
    assert benchmark["timings"]["shared_scene_vrt"]["n"] == 20


def test_postgis_equivalence():
    dsn = os.environ.get("EO_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("requires isolated PostGIS; not a passed spatial experiment")
    import psycopg

    from tools.eo_acceptance.spatial import run

    with psycopg.connect(dsn) as connection:
        result = run(connection)
    assert result["correctness_pass"]
    assert result["timings"]["baseline"]["n"] == 120
