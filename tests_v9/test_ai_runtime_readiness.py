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
