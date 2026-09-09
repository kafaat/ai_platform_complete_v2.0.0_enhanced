"""نقاطُ النهاية خلف بوّابة الهويّة — `EDGE-MODEL-ARTIFACT-INTEGRITY-01`.

المنطقُ الصرف مقيسٌ في `tests_v9/test_edge_model_artifact_integrity.py`. هنا يُقاس
أنّ **الاستدلالَ نفسَه** يقف عند البصمة (لا `/capabilities` وحدَها)، وأنّ 422/None
تبلغ العميلَ فعلاً عبر FastAPI.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
EDGE = ROOT / "services" / "edge-inference"
_HEADERS = {"X-Agent-Token": "test-agent-token"}


def _load_edge(monkeypatch, tmp_path, *, approve: bool):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "test-agent-token")
    monkeypatch.setenv("EDGE_SYNC_DIR", str(tmp_path / "sync"))
    monkeypatch.setenv("OFFLINE_MODE", "true")
    pest = tmp_path / "pest_detector_int8.onnx"
    yld = tmp_path / "yield_estimator_int8.onnx"
    pest.write_bytes(b"pest-bytes")
    yld.write_bytes(b"yield-bytes")
    monkeypatch.setenv("PEST_MODEL_PATH", str(pest))
    monkeypatch.setenv("YIELD_MODEL_PATH", str(yld))
    if approve:
        monkeypatch.setenv("PEST_MODEL_SHA256", hashlib.sha256(b"pest-bytes").hexdigest())
        monkeypatch.setenv("YIELD_MODEL_SHA256", hashlib.sha256(b"yield-bytes").hexdigest())
    else:
        monkeypatch.delenv("PEST_MODEL_SHA256", raising=False)
        monkeypatch.delenv("YIELD_MODEL_SHA256", raising=False)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    sys.path.insert(0, str(EDGE))
    spec = importlib.util.spec_from_file_location("edge_inference_main_gate_test", EDGE / "main.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _StubDetector:
    version = "stub"

    def predict(self, image_bytes, confidence_threshold=0.6):
        return [
            {
                "class_name": "aphid",
                "arabic_name": "منّ",
                "confidence": 0.95,
                "bbox": {"x1": 0.1},
                "affected_crops": ["wheat"],
                "action_policy": "observation_only",
                "severity": "medium",
            }
        ]


class _StubEstimator:
    def __init__(self, prediction=None, error=None):
        self._prediction = prediction
        self._error = error

    def extract_features(self, image_bytes):
        return {"greenness": 0.5}

    def predict_yield(self, features, crop, growth_stage):
        if self._error is not None:
            raise self._error
        return self._prediction


def test_inference_refuses_an_unapproved_model_even_though_the_file_exists(monkeypatch, tmp_path):
    """الملفُّ موجود، الكاشفُ كان سيُحمِّله بالمسار — البوّابةُ تقف قبله."""
    module = _load_edge(monkeypatch, tmp_path, approve=False)
    monkeypatch.setattr(module, "get_pest_detector", lambda: _StubDetector())
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/pest-detect",
        files={"file": ("leaf.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
        headers=_HEADERS,
    )
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "model_sha256_missing_or_invalid"


def test_an_approved_model_detects_and_the_alert_does_not_prescribe(monkeypatch, tmp_path):
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(module, "get_pest_detector", lambda: _StubDetector())
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/pest-detect",
        files={"file": ("leaf.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
        headers=_HEADERS,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["detections"][0]["action_policy"] == "observation_only"
    assert "recommended_action" not in payload["detections"][0]
    assert "الإجراء المقترح" not in payload["alert_ar"]


def test_empty_yield_features_are_a_422_not_a_zero_and_not_a_500(monkeypatch, tmp_path):
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(
        module,
        "get_yield_estimator",
        lambda: _StubEstimator(error=ValueError("yield_features_missing")),
    )
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/yield-estimate",
        files=[("files", ("a.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg"))],
        data={"image_count": "1"},
        headers=_HEADERS,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "yield_features_invalid_or_empty"


def test_yield_without_a_model_interval_publishes_none_and_the_limitation(monkeypatch, tmp_path):
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(
        module,
        "get_yield_estimator",
        lambda: _StubEstimator(
            prediction={"yield_kg_ha": 2500.0, "biomass_proxy": 0.4, "plant_count": 12}
        ),
    )
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/yield-estimate",
        files=[("files", ("a.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg"))],
        data={"image_count": "1"},
        headers=_HEADERS,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["estimated_yield_kg_ha"] == 2500.0
    assert payload["confidence_interval"] is None
    assert payload["limitations"] == ["yield_uncertainty_not_calibrated"]
