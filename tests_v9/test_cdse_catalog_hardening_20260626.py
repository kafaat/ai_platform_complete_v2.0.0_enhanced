from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_RASTER = Path(__file__).resolve().parent.parent / "services" / "raster-service"
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

import cdse_client  # noqa: E402


def test_rfc3339_normalizes_bare_dates_and_utc_offsets():
    assert cdse_client._to_rfc3339("2026-06-26") == "2026-06-26T00:00:00Z"
    assert cdse_client._to_rfc3339("2026-06-26T10:00:00+00:00") == "2026-06-26T10:00:00Z"
    assert cdse_client._to_rfc3339("2026-06-26T10:00:00Z") == "2026-06-26T10:00:00Z"


@pytest.mark.parametrize("value, expected", [(-5, 0.0), (40, 40.0), (120, 100.0), ("bad", 40.0)])
def test_cloud_percentage_is_provider_safe(value, expected):
    assert cdse_client._clamp_cloud_pct(value) == expected


def test_search_scenes_falls_back_when_provider_rejects_filter(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body
            self.text = str(body)

        def json(self):
            return self._body

    def fake_post(url, json, headers, timeout):  # noqa: A002
        calls.append(json)
        if len(calls) == 1:
            return Response(400, {"error": "bad filter"})
        return Response(
            200,
            {
                "features": [
                    {"id": "ok", "properties": {"eo:cloud_cover": 10}},
                    {"id": "cloudy", "properties": {"eo:cloud_cover": 90}},
                ]
            },
        )

    monkeypatch.setitem(sys.modules, "httpx", type("Httpx", (), {"post": staticmethod(fake_post)}))
    client = cdse_client.CdseClient(base_url="https://example.test")
    monkeypatch.setattr(client, "token", lambda: "token")

    scenes = client.search_scenes(
        bbox=[44.0, 15.0, 44.1, 15.1],
        time_from="2026-06-20",
        time_to="2026-06-26",
        max_cloud_pct=40,
    )

    assert [s["id"] for s in scenes] == ["ok"]
    assert "filter" in calls[0]
    assert "filter" not in calls[1]
    assert calls[0]["datetime"] == "2026-06-20T00:00:00Z/2026-06-26T00:00:00Z"


def test_search_scenes_rejects_invalid_bbox_before_network(monkeypatch):
    client = cdse_client.CdseClient(base_url="https://example.test")
    monkeypatch.setattr(client, "token", lambda: "token")
    with pytest.raises(ValueError):
        client.search_scenes(bbox=[44, 15, 43, 16], time_from="2026-06-20", time_to="2026-06-26")


@pytest.fixture
def catalog_api(monkeypatch):
    import importlib.util

    import httpx
    import imagery_source_gate
    import stac_search
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    client = cdse_client.CdseClient(base_url="https://catalog.invalid")
    monkeypatch.setattr(client, "token", lambda: "synthetic-token")
    monkeypatch.setattr(cdse_client, "get_client", lambda: client)
    monkeypatch.setattr(cdse_client, "is_configured", lambda: True)
    monkeypatch.setenv("CDSE_PROCESS_MAX_RETRIES", "0")
    monkeypatch.setattr(stac_search, "HISTORICAL_SEARCH_PROVIDER", "cdse")
    monkeypatch.setattr(imagery_source_gate, "enforce_enabled", lambda: False)
    spec = importlib.util.spec_from_file_location(
        "catalog_test_imagery_router", _RASTER / "routers" / "imagery_search.py"
    )
    router_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(router_module)
    app = FastAPI()
    app.include_router(router_module.router)
    with TestClient(app) as api:
        yield api, client, httpx


def _catalog_response(httpx, body, status=200):
    return httpx.Response(
        status, json=body, request=httpx.Request("POST", "https://catalog.invalid/search")
    )


def _best(api):
    return api.get("/v1/imagery/best", params={"west": 44, "south": 15, "east": 45, "north": 16})


@pytest.mark.parametrize("failure", ["timeout", "transport", "http", "malformed"])
def test_catalog_failure_is_not_a_successful_empty_best_scene(catalog_api, monkeypatch, failure):
    api, _client, httpx = catalog_api

    def post(*args, **kwargs):
        if failure == "timeout":
            raise httpx.ReadTimeout("private bearer synthetic-secret")
        if failure == "transport":
            raise httpx.ConnectError("private provider endpoint")
        if failure == "http":
            return _catalog_response(httpx, {"error": "private synthetic-secret"}, 503)
        return _catalog_response(httpx, {"error": "not a feature collection"})

    monkeypatch.setattr(httpx, "post", post)
    response = _best(api)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "cdse_catalog_unavailable"
    assert detail["provider"] == "cdse"
    assert (
        detail["reason"]
        == {
            "timeout": "timeout",
            "transport": "transport_error",
            "http": "http_error",
            "malformed": "invalid_response",
        }[failure]
    )
    assert "best" not in response.json()
    assert "synthetic-secret" not in response.text and "private" not in response.text


def test_valid_empty_catalog_preserves_successful_no_scene_contract(catalog_api, monkeypatch):
    api, client, httpx = catalog_api
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _catalog_response(httpx, {"features": []}))
    assert (
        client.search_scenes(bbox=[44, 15, 45, 16], time_from="2026-10-01", time_to="2026-10-14")
        == []
    )
    response = _best(api)
    assert response.status_code == 200
    assert response.json() == {
        "best": None,
        "candidates": 0,
        "note": "لا مشاهد ضمن المعايير — وسّع lookback أو max_cloud",
    }


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"features": None},
        {"features": {}},
        {"features": [None]},
        {"features": [{}]},
        {"features": [{"id": "a", "properties": []}]},
        {"features": [], "context": []},
        {"features": [], "context": {"next": []}},
    ],
)
def test_malformed_catalog_body_cannot_be_a_successful_empty_search(catalog_api, monkeypatch, body):
    api, _client, httpx = catalog_api
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _catalog_response(httpx, body))
    response = _best(api)
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "invalid_response"


def test_invalid_catalog_json_is_attributable_without_exposing_body(catalog_api, monkeypatch):
    api, _client, httpx = catalog_api
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: httpx.Response(200, content=b"private not-json")
    )
    response = _best(api)
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "invalid_response"
    assert "private" not in response.text


def _scene(scene_id="scene-1", cloud=10):
    return {
        "id": scene_id,
        "properties": {"datetime": "2026-10-12T10:00:00Z", "eo:cloud_cover": cloud},
        "bbox": [44, 15, 45, 16],
    }


def test_valid_scene_and_successful_cloud_filtered_empty_keep_contract(catalog_api, monkeypatch):
    api, _client, httpx = catalog_api
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: _catalog_response(httpx, {"features": [_scene()]})
    )
    response = _best(api)
    assert response.status_code == 200
    assert response.json()["best"]["item_id"] == "scene-1"
    assert response.json()["best"]["provider"] == "cdse"
    assert response.json()["candidates"] == 1
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: _catalog_response(httpx, {"features": [_scene(cloud=95)]})
    )
    response = _best(api)
    assert response.status_code == 200
    assert response.json()["best"] is None
    assert response.json()["candidates"] == 0


@pytest.mark.parametrize("failure", ["http", "timeout", "malformed"])
def test_later_catalog_page_failure_never_selects_best_from_partial_result(
    catalog_api, monkeypatch, failure
):
    api, _client, httpx = catalog_api
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 1:
            return _catalog_response(httpx, {"features": [_scene()], "context": {"next": "page2"}})
        if failure == "timeout":
            raise httpx.ReadTimeout("private second page")
        if failure == "http":
            return _catalog_response(httpx, {"error": "private second page"}, 429)
        return _catalog_response(httpx, {"features": None})

    monkeypatch.setattr(httpx, "post", post)
    response = _best(api)
    assert len(calls) == 2 and calls[1]["next"] == "page2"
    assert response.status_code == 503
    assert (
        response.json()["detail"]["reason"]
        == {"http": "http_error", "timeout": "timeout", "malformed": "invalid_response"}[failure]
    )
    if failure == "http":
        assert response.json()["detail"]["upstream_status"] == 429
    assert "best" not in response.json()


@pytest.mark.parametrize("recover", [False, True])
def test_catalog_transport_retry_budget_preserved(catalog_api, monkeypatch, recover):
    api, _client, httpx = catalog_api
    monkeypatch.setenv("CDSE_PROCESS_MAX_RETRIES", "1")
    delays = []
    monkeypatch.setattr(cdse_client.time, "sleep", delays.append)
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        if recover and len(calls) == 2:
            return _catalog_response(httpx, {"features": [_scene()]})
        raise httpx.ConnectError("private network")

    monkeypatch.setattr(httpx, "post", post)
    response = _best(api)
    assert len(calls) == 2 and len(delays) == 1
    assert response.status_code == (200 if recover else 503)
    if not recover:
        assert response.json()["detail"]["reason"] == "transport_error"


@pytest.mark.parametrize(
    "endpoint,extra",
    [
        ("/v1/imagery/search/recent", {}),
        ("/v1/imagery/search/season", {"sowing_date": "2026-10-01"}),
    ],
)
def test_other_catalog_search_routes_propagate_same_failure(
    catalog_api, monkeypatch, endpoint, extra
):
    api, _client, httpx = catalog_api

    def post(*a, **k):
        raise httpx.ReadTimeout("private timeout")

    monkeypatch.setattr(httpx, "post", post)
    response = api.get(endpoint, params={"west": 44, "south": 15, "east": 45, "north": 16, **extra})
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "timeout"


def test_unexpected_catalog_provider_exception_is_sanitized(catalog_api, monkeypatch):
    api, client, _httpx = catalog_api

    def search(**kwargs):
        raise RuntimeError("private access token synthetic-secret")

    monkeypatch.setattr(client, "search_scenes", search)
    response = _best(api)
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "cdse_catalog_unavailable",
        "provider": "cdse",
        "reason": "provider_error",
    }


@pytest.mark.parametrize(
    "response_body,status,expected",
    [
        (
            {"features": [{"id": "unknown", "properties": {"eo:cloud_cover": "bad"}}]},
            200,
            "acquisitions_cloud_cover_unknown",
        ),
        (
            {"features": [{"id": "invalid", "properties": {"eo:cloud_cover": 101}}]},
            200,
            "acquisitions_cloud_cover_unknown",
        ),
        (
            {"features": [{"id": "invalid", "properties": {"eo:cloud_cover": -1}}]},
            200,
            "acquisitions_cloud_cover_unknown",
        ),
        (
            {
                "features": [{"id": "cloudy", "properties": {"eo:cloud_cover": 90}}],
                "context": {"next": "page-two"},
            },
            200,
            "catalogue_unavailable",
        ),
        ({"features": []}, 200, "no_acquisition"),
        ({"error": "upstream unavailable"}, 503, "catalogue_unavailable"),
    ],
)
def test_failure_probe_uses_unfiltered_complete_single_catalogue_response(
    monkeypatch, response_body, status, expected
):
    import cdse_diagnostics
    import httpx
    import raster_cdse_tile_runtime as runtime

    calls = []

    def post(url, **kwargs):
        calls.append(kwargs["json"])
        # A second request must not hide a pagination/fallback error.
        if len(calls) > 1:
            raise AssertionError("diagnostic catalogue request exceeded one call")
        return httpx.Response(status, json=response_body, request=httpx.Request("POST", url))

    monkeypatch.setenv("CDSE_DIAGNOSTIC_CATALOGUE_PROBE", "1")
    monkeypatch.setattr(cdse_diagnostics, "_probe_cache", {})
    monkeypatch.setattr(httpx, "post", post)
    client = cdse_client.CdseClient(base_url="https://catalogue.invalid")
    monkeypatch.setattr(client, "token", lambda: "injected-test-token")
    result = runtime.catalogue_probe(
        client,
        bbox=[44, 15, 45, 16],
        geometry=None,
        date_from="2026-10-01",
        date_to="2026-10-14",
    )
    assert result == expected
    assert len(calls) == 1
    assert "filter" not in calls[0] and "filter-lang" not in calls[0]
