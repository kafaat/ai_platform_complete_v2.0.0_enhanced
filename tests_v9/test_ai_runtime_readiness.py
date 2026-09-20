"""Runtime readiness must describe usable capabilities, including import failures."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "status,body",
    [
        (401, {"status": "ready"}),
        (403, {"status": "ready"}),
        (404, {"detail": "Not Found"}),
        (503, {"status": "ready"}),
        (200, {"status": "degraded"}),
        (200, {"status": "ready", "ready": False}),
        (200, []),
        (200, {}),
        (200, {"status": "ready", "ready": "true"}),
    ],
)
def test_agronomist_rejects_unready_dependency(monkeypatch, status, body):
    from services.ai_agronomist import main

    def reply(request):
        if "rag-retrieval" in request.url.host:
            return httpx.Response(status, json=body)
        return httpx.Response(200, json={"status": "ready"})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        main.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(reply), **kwargs),
    )
    client = TestClient(main.app)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["detail"]["dependencies"]["rag"] is False
    assert client.get("/healthz").status_code == 200


def test_agronomist_ready_only_with_ready_dependencies(monkeypatch):
    from services.ai_agronomist import main

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        main.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json={"status": "ready"})
            ),
            **kwargs,
        ),
    )
    response = TestClient(main.app).get("/readyz")
    assert response.status_code == 200
    assert all(response.json()["dependencies"].values())


@pytest.mark.parametrize("failure", [None, "connect", "schema", "unsafe_role", "owner_lookup"])
@pytest.mark.asyncio
async def test_database_readiness_failure_modes(monkeypatch, failure):
    import asyncpg

    from shared.dependency_readiness import database_ready

    class Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class Connection:
        closed = False

        def transaction(self, *, readonly):
            assert readonly
            return Transaction()

        async def execute(self, sql, *args):
            return "SELECT 1"

        async def fetchval(self, sql, *args):
            if "pg_roles" in sql:
                return failure != "unsafe_role"
            return failure != "owner_lookup"

        async def fetch(self, sql):
            if failure == "schema":
                raise RuntimeError("fixture secret must not escape")
            assert "LIMIT 0" in sql
            return []

        async def close(self, **kwargs):
            self.closed = True

    connection = Connection()

    async def connect(*args, **kwargs):
        if failure == "connect":
            raise OSError("fixture secret must not escape")
        return connection

    monkeypatch.setattr(asyncpg, "connect", connect)
    ready = await database_ready(
        "postgresql://fixture", table="raster_assets", columns="field_id", owner_lookup=True
    )
    assert ready is (failure is None)
    assert connection.closed is (failure != "connect")
    assert await database_ready("", table="fields", columns="field_id") is False


@pytest.mark.parametrize("failure", [None, "connect", "ping", "close"])
@pytest.mark.asyncio
async def test_replay_store_probe_handles_failure_without_leaking_credentials(monkeypatch, failure):
    from redis.asyncio import Redis

    from shared.dependency_readiness import redis_ready

    class Client:
        close_attempted = False

        async def ping(self):
            if failure == "ping":
                raise TimeoutError("fixture credentials must not escape")
            return True

        async def aclose(self):
            self.close_attempted = True
            if failure == "close":
                raise OSError("fixture credentials must not escape")

    client = Client()

    def connect(*args, **kwargs):
        if failure == "connect":
            raise OSError("fixture credentials must not escape")
        return client

    monkeypatch.setattr(Redis, "from_url", connect)
    assert await redis_ready("redis://fixture") is (failure in {None, "close"})
    assert client.close_attempted is (failure != "connect")
    assert await redis_ready("") is False


def test_work_directory_probe_preserves_existing_files(tmp_path):
    from shared.dependency_readiness import writable_directory_ready

    asset = tmp_path / "existing.tif"
    asset.write_bytes(b"existing asset")
    assert writable_directory_ready(str(tmp_path)) is True
    assert asset.read_bytes() == b"existing asset"
    assert list(tmp_path.iterdir()) == [asset]
    assert writable_directory_ready(str(asset)) is False


@pytest.mark.parametrize(
    "catalog_status,database,storage,expected",
    [
        (200, True, True, 200),
        (404, True, True, 503),
        (200, False, True, 503),
        (200, True, False, 503),
    ],
)
def test_raster_readiness_requires_catalog_schema_and_storage(
    monkeypatch, catalog_status, database, storage, expected
):
    from fastapi import FastAPI

    directory = ROOT / "services/raster-service"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "raster_observability_readiness", directory / "routers/observability.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def db(*args, **kwargs):
        return database

    monkeypatch.setattr(module, "database_ready", db)
    monkeypatch.setattr(module, "writable_directory_ready", lambda path: storage)
    monkeypatch.setattr(module, "_terrain_soil_readiness", lambda: {})
    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    catalog_status, json={"type": "Catalog", "stac_version": "1.0.0"}
                )
            ),
            **kwargs,
        ),
    )
    app = FastAPI()
    app.include_router(module.router)
    response = TestClient(app).get("/readyz")
    assert response.status_code == expected
    assert response.json()["ready"] is (expected == 200)


def _segmentation(monkeypatch):
    directory = ROOT / "services/field-segmentation"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("readiness_segmentation", directory / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "SEGMENTATION_BACKEND", "sam2")
    monkeypatch.setattr(module, "SEGMENTATION_INFERENCE_URL", "http://sam2:8080/v1/predict")
    return module


@pytest.mark.parametrize(
    "status,body,ready",
    [
        (200, {"status": "ready", "model_loaded": True}, True),
        (200, {"status": "degraded", "model_loaded": False}, False),
        (503, {"status": "ready", "model_loaded": True}, False),
        (200, {"status": "ready"}, False),
        (200, {"status": "ready", "model_loaded": True, "ready": False}, False),
        (200, [], False),
    ],
)
def test_segmentation_checks_loaded_model_not_just_configuration(monkeypatch, status, body, ready):
    module = _segmentation(monkeypatch)
    urls = []

    def respond(request):
        urls.append(str(request.url))
        return httpx.Response(status, json=body)

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs),
    )
    client = TestClient(module.app)
    response = client.get("/readyz")
    assert response.status_code == (200 if ready else 503)
    assert response.json()["model_configured"] is True
    assert response.json()["model_ready"] is ready
    assert response.json()["capabilities"]["manual"]["ready"] is True
    assert response.json()["capabilities"]["auto"]["ready"] is ready
    assert urls == ["http://sam2:8080/readyz"]
    assert client.get("/healthz").status_code == 200


def test_manual_only_segmentation_remains_ready_without_network(monkeypatch):
    module = _segmentation(monkeypatch)
    monkeypatch.setattr(module, "SEGMENTATION_BACKEND", "")
    response = TestClient(module.app).get("/readyz")
    assert response.status_code == 200
    assert response.json()["model_ready"] is False
    assert response.json()["capabilities"]["auto"]["reason"] == "model_not_configured"


def test_segmentation_backend_timeout_fails_readiness(monkeypatch):
    module = _segmentation(monkeypatch)

    def timeout(request):
        raise httpx.ReadTimeout("unavailable", request=request)

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(timeout), **kwargs),
    )
    response = TestClient(module.app).get("/readyz")
    assert response.status_code == 503
    assert response.json()["capabilities"]["hybrid"]["reason"] == "inference_unavailable"


@pytest.mark.parametrize("broken_store", [False, True])
def test_vegetation_imports_real_routes_and_reports_unusable_sqlite(tmp_path, broken_store):
    db_path = tmp_path / "anomalies.db"
    if broken_store:
        db_path.mkdir()  # sqlite.connect cannot open a directory, even as root.
    directory = ROOT / "services/vegetation-analysis-service"
    code = """
import json
import main
from fastapi.testclient import TestClient
client = TestClient(main.app)
r = client.get('/readyz')
print(json.dumps({'code': r.status_code, 'body': r.json(),
                 'health': client.get('/healthz').status_code,
                 'routes': [r.path for r in main.app.routes if hasattr(r, 'path')]}))
"""
    env = dict(
        os.environ,
        VEGETATION_REAL_ONLY="0",
        VEGETATION_ANOMALY_STORE="sqlite",
        VEGETATION_ANOMALY_DB_PATH=str(db_path),
        PYTHONPATH=str(directory) + os.pathsep + str(ROOT),
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    assert report["health"] == 200
    assert report["code"] == (503 if broken_store else 200)
    assert report["body"]["ready"] is (not broken_store)
    failures = report["body"]["router_import_failures"]
    if broken_store:
        assert failures["anomalies"] == "OperationalError"
        assert failures["diagnoses"] == "OperationalError"
    else:
        assert failures == {}
        assert any("anomalies" in path for path in report["routes"])
        assert any("diagnos" in path for path in report["routes"])
