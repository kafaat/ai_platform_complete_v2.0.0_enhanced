"""Exercise the real COG transport and default deployment edges; no live services."""

from __future__ import annotations

import base64
import graphlib
import importlib.util
import re
import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from shared.gis import cog_tile_proxy

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a4P8AAAAASUVORK5CYII="
)


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setenv("COG_TILE_ALLOWED_HOSTS", "cogs.example.test")
    original = httpx.AsyncClient
    requests = []

    def install(status=200, content=PNG, content_type="image/png", error=None):
        def handle(request):
            requests.append(request)
            if error:
                raise error
            return httpx.Response(status, content=content, headers={"Content-Type": content_type})

        monkeypatch.setattr(
            cog_tile_proxy.httpx,
            "AsyncClient",
            lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
        )

    install()
    return requests, install


async def test_backend_receives_encoded_source_and_returns_png(transport):
    requests, _ = transport
    source = "https://cogs.example.test/a.tif?signature=a&expires=42"
    result = await cog_tile_proxy.fetch_registered_cog_tile(
        source, 2, 1, 1, base_url="http://raster-tiler-service:8088", colormap="viridis"
    )
    assert result == PNG
    assert len(requests) == 1
    request = requests[0]
    assert request.url.path == "/cog/tiles/WebMercatorQuad/2/1/1.png"
    assert request.url.params["url"] == source
    assert "expires" not in request.url.params
    assert "authorization" not in request.headers


@pytest.mark.parametrize(
    "source",
    [
        "file:///etc/passwd",
        "s3://private/another-tenant.tif",
        "https://127.0.0.1/private.tif",
        "https://cogs.example.test.evil.test/a.tif",
        "https://user:password@cogs.example.test/a.tif",
        "https://cogs.example.test:9000/a.tif",
    ],
)
async def test_untrusted_source_is_rejected_before_transport(source, transport):
    requests, _ = transport
    with pytest.raises(HTTPException) as exc:
        await cog_tile_proxy.fetch_registered_cog_tile(
            source, 2, 1, 1, base_url="http://raster-tiler-service:8088"
        )
    assert exc.value.status_code == 422
    assert requests == []


@pytest.mark.parametrize("coordinates", [(-1, 0, 0), (23, 0, 0), (2, 4, 0), (2, 0, -1)])
async def test_invalid_coordinates_do_not_reach_backend(coordinates, transport):
    requests, _ = transport
    with pytest.raises(HTTPException) as exc:
        await cog_tile_proxy.fetch_registered_cog_tile(
            "https://cogs.example.test/a.tif", *coordinates, base_url="http://tiler:8088"
        )
    assert exc.value.status_code == 422
    assert not requests


async def test_unconfigured_allowlist_fails_closed(monkeypatch, transport):
    monkeypatch.delenv("COG_TILE_ALLOWED_HOSTS")
    with pytest.raises(HTTPException) as exc:
        await cog_tile_proxy.fetch_registered_cog_tile(
            "https://cogs.example.test/a.tif", 2, 1, 1, base_url="http://tiler:8088"
        )
    assert exc.value.status_code == 503
    assert transport[0] == []


@pytest.mark.parametrize(
    "status,content,content_type",
    [
        (302, b"", "image/png"),
        (500, b"", "image/png"),
        (200, b"<html/>", "text/html"),
        (200, b"not a png", "image/png"),
        (200, PNG + b"x" * (2 * 1024 * 1024), "image/png"),
    ],
)
async def test_bad_backend_response_is_not_a_successful_tile(
    status, content, content_type, transport
):
    transport[1](status, content, content_type)
    with pytest.raises(HTTPException) as exc:
        await cog_tile_proxy.fetch_registered_cog_tile(
            "https://cogs.example.test/a.tif", 2, 1, 1, base_url="http://tiler:8088"
        )
    assert exc.value.status_code == 502


async def test_backend_timeout_has_named_failure(transport):
    transport[1](error=httpx.ReadTimeout("private transport details"))
    with pytest.raises(HTTPException) as exc:
        await cog_tile_proxy.fetch_registered_cog_tile(
            "https://cogs.example.test/a.tif", 2, 1, 1, base_url="http://tiler:8088"
        )
    assert exc.value.detail == "cog_tile_backend_unavailable"


def test_canonical_tiler_is_reachable_and_gateway_waits_for_its_upstreams():
    services = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))[
        "services"
    ]
    list(
        graphlib.TopologicalSorter(
            {k: set(v.get("depends_on", {})) for k, v in services.items()}
        ).static_order()
    )
    for name in ("sahool-platform", "sahool-raster-service"):
        caller = services[name]
        assert "raster-tiler-service:8088" in caller["environment"]["TITILER_URL"]
        assert set(caller["networks"]) & set(services["raster-tiler-service"]["networks"])
        assert caller["depends_on"]["raster-tiler-service"]["condition"] == "service_healthy"
    conf = "\n".join(
        line.split("#", 1)[0]
        for line in (ROOT / "nginx/nginx.v9.conf").read_text(encoding="utf-8").splitlines()
    )
    hosts = re.findall(r"upstream\s+\w+\s*\{\s*server\s+([\w-]+):\d+", conf)
    assert hosts
    for host in hosts:
        assert services["sahool-nginx"]["depends_on"][host]["condition"] == "service_healthy"
    assert services["sahool-titiler"]["profiles"] == ["legacy-tiler"]


def test_erp_credentials_without_explicit_target_do_not_invent_a_host(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "connectivity_erp_provider", ROOT / "services/odoo-bridge/erp_provider.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("ERP_PROVIDER", "erpnext")
    monkeypatch.setenv("ERPNEXT_API_KEY", "test-key")
    monkeypatch.setenv("ERPNEXT_API_SECRET", "test-secret")
    monkeypatch.delenv("ERPNEXT_URL", raising=False)
    assert module.get_erp_provider().name == "none"
    monkeypatch.setenv("ERPNEXT_URL", "https://erp.example.test")
    assert module.get_erp_provider().name == "erpnext"


def test_registry_tile_route_authorizes_before_contacting_backend(monkeypatch, transport):
    """Actual router + actual transport; identity and tenant DB are explicit test adapters."""

    class User(BaseModel):
        tenant_id: str

    class Permissions:
        def __getattr__(self, name):
            return name

    def require_permission(_permission):
        def authenticate(authorization: str | None = Header(None)):
            if authorization not in {"tenant-a", "tenant-b"}:
                raise HTTPException(401, "authentication_required")
            return User(tenant_id=authorization)

        return authenticate

    record = {
        "id": "raster-1",
        "tenant_id": "tenant-a",
        "field_id": "field-1",
        "product_date": "2026-09-10",
        "index_type": "ndvi",
        "cog_url": "https://cogs.example.test/a.tif",
        "cloud_pct": 0,
        "quality_score": 100,
        "scene_id": None,
        "resolution_m": 10,
        "bbox": None,
        "bands": None,
        "metadata": None,
    }

    @asynccontextmanager
    async def tenant_connection(user):
        class Connection:
            async def fetchrow(self, _sql, raster_id):
                return (
                    record if user.tenant_id == "tenant-a" and raster_id == record["id"] else None
                )

        yield Connection()

    stub = types.ModuleType("api.main")
    stub.UserSchema = User
    stub.Permission = Permissions()
    stub.require_permission = require_permission
    stub.tenant_connection = tenant_connection
    stub._db_unavailable = lambda *_: HTTPException(503, "database_unavailable")
    monkeypatch.setitem(sys.modules, "api.main", stub)
    name = "connectivity_gis_router"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "services/sahool-platform/api/routers/gis_cloud_native.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    app = FastAPI()
    app.include_router(module.router)
    monkeypatch.setenv("TITILER_URL", "http://raster-tiler-service:8088")
    client = TestClient(app)
    base = "/api/v1/gis/cloud-native/rasters/raster-1"
    tilejson = client.get(base + "/tilejson.json", headers={"Authorization": "tenant-a"})
    assert tilejson.status_code == 200
    tile = tilejson.json()["tiles"][0].format(z=2, x=1, y=1)
    assert client.get(tile).status_code == 401
    assert client.get(tile, headers={"Authorization": "tenant-b"}).status_code == 404
    assert transport[0] == []
    response = client.get(tile, headers={"Authorization": "tenant-a"})
    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["cache-control"] == "private, no-store"
    assert len(transport[0]) == 1
