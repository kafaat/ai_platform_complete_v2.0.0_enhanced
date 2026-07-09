from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
EDGE = ROOT / "services" / "edge-inference"


def _load_edge(monkeypatch, *, preserve_model_env: bool = False):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "test-agent-token")
    # CI runner بلا صلاحيّة كتابة على /data — وجِّه sync_queue لمجلّد مؤقّت.
    import tempfile

    monkeypatch.setenv("EDGE_SYNC_DIR", tempfile.mkdtemp(prefix="edge-sync-"))
    if not preserve_model_env:
        monkeypatch.delenv("PEST_MODEL_PATH", raising=False)
        monkeypatch.delenv("YIELD_MODEL_PATH", raising=False)
        monkeypatch.setenv("MODEL_CACHE", str(EDGE / "tests" / "missing-models"))
    sys.path.insert(0, str(EDGE))
    spec = importlib.util.spec_from_file_location("edge_inference_main_test", EDGE / "main.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_capabilities_report_missing_models_without_claiming_active(monkeypatch):
    module = _load_edge(monkeypatch)
    client = TestClient(module.app)
    payload = client.get("/capabilities").json()
    assert payload["agent_token_configured"] is True
    assert payload["capabilities"]["pest_detect"]["active"] is False
    assert payload["capabilities"]["pest_detect"]["reason"] == "model_file_missing"
    assert payload["capabilities"]["yield_estimate"]["active"] is False


def test_readyz_is_degraded_when_models_are_absent(monkeypatch):
    module = _load_edge(monkeypatch)
    client = TestClient(module.app)
    response = client.get("/readyz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["readiness_mode"] == "partial"
    assert payload["active_capability_count"] == 0
    assert payload["all_required_models_active"] is False
    assert payload["model_policy"].startswith("partial-readiness")


def test_strict_readyz_returns_503_when_models_are_absent(monkeypatch):
    monkeypatch.setenv("EDGE_READINESS_MODE", "strict")
    module = _load_edge(monkeypatch)
    client = TestClient(module.app)
    response = client.get("/readyz")
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["readiness_mode"] == "strict"
    assert payload["model_policy"].startswith("strict-readiness")


def test_wrong_or_missing_agent_token_is_rejected(monkeypatch):
    module = _load_edge(monkeypatch)
    client = TestClient(module.app)
    response = client.post("/sync/trigger", headers={"X-Agent-Token": "wrong"})
    assert response.status_code == 401


def test_strict_readyz_is_ready_when_required_models_are_present(monkeypatch, tmp_path):
    pest = tmp_path / "pest_detector_int8.onnx"
    yld = tmp_path / "yield_estimator_int8.onnx"
    pest.write_bytes(b"placeholder-for-presence-only")
    yld.write_bytes(b"placeholder-for-presence-only")
    monkeypatch.setenv("EDGE_READINESS_MODE", "strict")
    monkeypatch.setenv("PEST_MODEL_PATH", str(pest))
    monkeypatch.setenv("YIELD_MODEL_PATH", str(yld))
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name: object() if name == "onnxruntime" else object()
    )

    module = _load_edge(monkeypatch, preserve_model_env=True)
    client = TestClient(module.app)
    response = client.get("/readyz")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ready"
    assert payload["readiness_mode"] == "strict"
    assert payload["all_required_models_active"] is True
    assert payload["active_capability_count"] == 2


def test_production_required_forces_strict_readyz_when_models_are_absent(monkeypatch):
    monkeypatch.setenv("EDGE_READINESS_MODE", "partial")
    monkeypatch.setenv("EDGE_PRODUCTION_REQUIRED", "true")
    module = _load_edge(monkeypatch)
    client = TestClient(module.app)
    response = client.get("/readyz")
    payload = response.json()

    assert response.status_code == 503
    assert payload["status"] == "degraded"
    assert payload["readiness_mode"] == "partial"
    assert payload["production_required"] is True
    assert "EDGE_PRODUCTION_REQUIRED forces strict readiness" in payload["model_policy"]
