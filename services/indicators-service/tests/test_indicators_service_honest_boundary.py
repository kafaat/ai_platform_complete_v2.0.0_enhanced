from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

MODULE_PATH = Path(__file__).resolve().parents[1] / "main.py"
spec = importlib.util.spec_from_file_location("indicators_service_main", MODULE_PATH)
assert spec and spec.loader
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)
client = TestClient(main.app)


def test_indicators_service_reports_canonical_adapter_readiness():
    response = client.get("/readyz")
    assert response.status_code == 200
    ready = response.json()
    assert ready["status"] == "ready"
    assert ready["implemented_runtime"] is True
    assert ready["runtime_role"] == "canonical-observation-adapter"
    assert ready["spectral_compute"] is False
    assert ready["observed_spectral_owner"] == "raster-service"


def test_indicator_compute_fails_closed_not_fabricated():
    response = client.post("/v1/indicators/compute")
    assert response.status_code == 409
    assert "raster-service" in response.json()["detail"]


def test_canonical_catalog_is_published():
    response = client.get("/v1/indicators/catalog")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "canonical-indicator-ownership-manifest"
    assert any(
        item["id"] == "ndvi" and item["owner"] == "raster-service" for item in body["indicators"]
    )
