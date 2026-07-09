from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE = Path(__file__).resolve().parents[1]


def _load_main():
    spec = importlib.util.spec_from_file_location("indicators_service_main", SERVICE / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_indicators_service_reports_health_only_degraded_readiness():
    module = _load_main()
    client = TestClient(module.app)
    assert client.get("/healthz").json()["status"] == "alive"
    ready = client.get("/readyz").json()
    assert ready["status"] == "degraded"
    assert ready["implemented_runtime"] is False
    assert ready["health_only"] is True
    caps = client.get("/capabilities").json()
    assert caps["capabilities"]["indicator_compute"] is False


def test_indicator_compute_fails_closed_not_fabricated():
    module = _load_main()
    client = TestClient(module.app)
    response = client.post("/v1/indicators/compute")
    assert response.status_code == 501
    assert "No fabricated" in response.json()["detail"]
