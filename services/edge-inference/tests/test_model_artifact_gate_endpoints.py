"""نقاطُ النهاية خلف بوّابة الهويّة — `EDGE-MODEL-ARTIFACT-INTEGRITY-01`.

المنطقُ الصرف مقيسٌ في `tests_v9/test_edge_model_artifact_integrity.py`. هنا يُقاس
أنّ **الاستدلالَ نفسَه** يقف عند البصمة (لا `/capabilities` وحدَها)، وأنّ 422/None
تبلغ العميلَ فعلاً عبر FastAPI.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
EDGE = ROOT / "services" / "edge-inference"
_HEADERS = {"X-Agent-Token": "test-agent-token"}
_EDGE_KEY = "w0-07-edge-assertion-key-0123456789abcdef"
_TENANT_B = "22222222-2222-2222-2222-222222222222"


def _signed(path: str, tenant: str = _TENANT_B, service: str = "video-processor", key=_EDGE_KEY):
    """Agent token + a tenant assertion for ``path`` (W0-07)."""
    from shared.security.tenant_assertion_headers import tenant_assertion_headers

    return {
        **_HEADERS,
        **tenant_assertion_headers(
            key=key, key_id="current", service=service, tenant_id=tenant, method="POST", path=path
        ),
    }


def _load_edge(monkeypatch, tmp_path, *, approve: bool):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "test-agent-token")
    monkeypatch.setenv("EDGE_DEVICE_ID", "edge-unit-device")
    monkeypatch.setenv("EDGE_SYNC_DIR", str(tmp_path / "sync"))
    monkeypatch.setenv("OFFLINE_MODE", "true")
    monkeypatch.setenv("EDGE_TENANT_ASSERTION_KEY", _EDGE_KEY)
    monkeypatch.delenv("EDGE_INFERENCE_ALLOWED_CALLERS", raising=False)
    for key in ("PEST_MODEL_BUNDLE_MANIFEST", "YIELD_MODEL_BUNDLE_MANIFEST", "PEST_LABELS_PATH"):
        monkeypatch.delenv(key, raising=False)
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
    monkeypatch.syspath_prepend(str(EDGE))
    from models import model_bundle

    monkeypatch.setattr(
        model_bundle,
        "open_session",
        lambda weights, _device: _FakeOnnxSession(
            _manifest_len(), yield_kg_ha=2500.0 if weights == b"yield-bytes" else None
        ),
    )
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
    monkeypatch.setattr(module, "get_pest_detector", lambda _bundle: _StubDetector())
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/pest-detect",
        data={"field_id": "field-unit"},
        files={"file": ("leaf.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
        headers=_HEADERS,
    )
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "model_sha256_missing_or_invalid"


def test_an_approved_model_detects_and_the_alert_does_not_prescribe(monkeypatch, tmp_path):
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(module, "get_pest_detector", lambda _bundle: _StubDetector())
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/pest-detect",
        data={"field_id": "field-unit"},
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
        lambda _bundle: _StubEstimator(error=ValueError("yield_features_missing")),
    )
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/yield-estimate",
        files=[("files", ("a.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg"))],
        data={"image_count": "1", "field_id": "field-unit"},
        headers=_HEADERS,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "yield_features_invalid_or_empty"


def test_yield_without_a_model_interval_publishes_none_and_the_limitation(monkeypatch, tmp_path):
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(
        module,
        "get_yield_estimator",
        lambda _bundle: _StubEstimator(
            prediction={"yield_kg_ha": 2500.0, "biomass_proxy": 0.4, "plant_count": 12}
        ),
    )
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/yield-estimate",
        files=[("files", ("a.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg"))],
        data={"image_count": "1", "field_id": "field-unit"},
        headers=_HEADERS,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["estimated_yield_kg_ha"] == 2500.0
    assert payload["confidence_interval"] is None
    assert payload["limitations"] == ["yield_uncertainty_not_calibrated"]


def _queued(tmp_path) -> list[Path]:
    return sorted((tmp_path / "sync").glob("*.json"))


def test_pest_detect_without_a_field_detects_but_never_queues_a_sync(monkeypatch, tmp_path):
    """إطارُ بثٍّ غير مربوط بحقل: كان video-processor يُرسِل field_id="stream" فتُزامَن
    نتيجةٌ تردّ عليها المنصّة 404 وتُعاد محاولتها بلا نهاية. بلا field_id ⇒ لا مزامنة."""
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(module, "get_pest_detector", lambda _bundle: _StubDetector())
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/pest-detect",
        files={"file": ("frame.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
        headers=_HEADERS,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["sync_status"] == "not_synced_no_field"
    assert payload["field_id"] is None
    assert payload["crop"] is None
    assert payload["detections"][0]["class_name"] == "aphid"
    assert _queued(tmp_path) == []


def test_pest_detect_does_not_invent_a_crop_for_a_bound_field(monkeypatch, tmp_path):
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(module, "get_pest_detector", lambda _bundle: _StubDetector())
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/pest-detect",
        data={"field_id": "field-unit"},
        files={"file": ("frame.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
        headers=_signed("/v1/inference/pest-detect"),
    )
    assert response.status_code == 200
    assert response.json()["crop"] is None
    assert response.json()["sync_status"] == "queued"
    [queued] = _queued(tmp_path)
    assert '"field_id": "field-unit"' in queued.read_text(encoding="utf-8")


def _png(width: int, height: int) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("1", (width, height), 0).save(buffer, "PNG")
    return buffer.getvalue()


class _DecodingDetector(_StubDetector):
    """يفكّ الصورة بالمسار الحقيقيّ للكاشف قبل الكشف الوهميّ."""

    def predict(self, image_bytes, confidence_threshold=0.6):
        from models.pest_detector import decode_rgb

        decode_rgb(image_bytes)
        return super().predict(image_bytes, confidence_threshold)


class _DecodingEstimator(_StubEstimator):
    def extract_features(self, image_bytes):
        from models.yield_estimator import decode_rgb

        decode_rgb(image_bytes)
        return super().extract_features(image_bytes)


def test_pixel_cap_is_a_413_on_both_inference_endpoints(monkeypatch, tmp_path):
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setenv("EDGE_MAX_IMAGE_PIXELS", "10000")
    monkeypatch.setattr(module, "get_pest_detector", lambda _bundle: _DecodingDetector())
    monkeypatch.setattr(
        module,
        "get_yield_estimator",
        lambda _bundle: _DecodingEstimator(prediction={"yield_kg_ha": 1.0}),
    )
    client = TestClient(module.app)
    big = _png(200, 100)  # 20 000 px
    pest = client.post(
        "/v1/inference/pest-detect",
        data={"field_id": "field-unit"},
        files={"file": ("a.png", io.BytesIO(big), "image/png")},
        headers=_HEADERS,
    )
    yld = client.post(
        "/v1/inference/yield-estimate",
        files=[("files", ("a.png", io.BytesIO(big), "image/png"))],
        data={"image_count": "1", "field_id": "field-unit"},
        headers=_HEADERS,
    )
    assert pest.status_code == 413
    assert yld.status_code == 413


def test_uploads_are_read_with_a_size_bound_not_whole(monkeypatch, tmp_path):
    from starlette.datastructures import UploadFile

    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(module, "get_pest_detector", lambda _bundle: _StubDetector())
    monkeypatch.setattr(
        module,
        "get_yield_estimator",
        lambda _bundle: _StubEstimator(prediction={"yield_kg_ha": 1.0}),
    )
    sizes: list[int] = []
    original = UploadFile.read

    async def _recording_read(self, size: int = -1):
        sizes.append(size)
        return await original(self, size)

    monkeypatch.setattr(UploadFile, "read", _recording_read)
    client = TestClient(module.app)
    client.post(
        "/v1/inference/pest-detect",
        data={"field_id": "field-unit"},
        files={"file": ("a.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
        headers=_HEADERS,
    )
    client.post(
        "/v1/inference/yield-estimate",
        files=[("files", ("a.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg"))],
        data={"image_count": "1", "field_id": "field-unit"},
        headers=_HEADERS,
    )
    assert len(sizes) == 2
    assert all(0 < size <= 10 * 1024 * 1024 + 1 for size in sizes)


def test_a_synced_detection_carries_the_gate_artifact_sha_and_the_input_digest(
    monkeypatch, tmp_path
):
    """نسبُ الكشف: البصمةُ المُزامَنة هي **حكمُ البوّابة** (بايتات المصنوعة المثبَّتة)،
    وبصمةُ المدخل بايتاتُ الصورة المرفوعة — لا قيمةُ بيئةٍ ولا «معايَر» مُدّعى."""
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(module, "get_pest_detector", lambda _bundle: _StubDetector())
    image = b"\xff\xd8\xff-leaf"
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/pest-detect",
        data={"field_id": "field-unit", "confidence_threshold": "0.7"},
        files={"file": ("leaf.jpg", io.BytesIO(image), "image/jpeg")},
        headers=_signed("/v1/inference/pest-detect"),
    )
    assert response.status_code == 200
    gate_sha = module._model_capability("pest_detector_int8.onnx")["actual_sha256"]
    assert gate_sha == hashlib.sha256(b"pest-bytes").hexdigest()
    [queued] = _queued(tmp_path)
    provenance = json.loads(queued.read_text(encoding="utf-8"))["data"]["provenance"]
    assert provenance["artifact_sha256"] == gate_sha
    assert len(provenance["bundle_sha256"]) == 64
    assert provenance["input_sha256"] == hashlib.sha256(image).hexdigest()
    assert provenance["model_id"] == "pest_detector_int8.onnx"
    assert provenance["model_version"] == "stub"
    assert provenance["threshold"] == 0.7
    assert provenance["calibrated"] is False
    assert response.json()["provenance"] == provenance


# ── W0-07 (scout-1) and W0-08 (scout-2) ─────────────────────────────────────────────────────


def _pest(client, headers, field_id="field-unit"):
    return client.post(
        "/v1/inference/pest-detect",
        data={"field_id": field_id},
        files={"file": ("leaf.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
        headers=headers,
    )


def test_a_bound_detection_is_queued_under_the_tenant_its_caller_signed(monkeypatch, tmp_path):
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(module, "get_pest_detector", lambda _bundle: _StubDetector())
    client = TestClient(module.app)
    response = _pest(client, _signed("/v1/inference/pest-detect"))
    assert response.status_code == 200, response.text
    assert response.json()["sync_status"] == "queued", response.json()
    [queued] = _queued(tmp_path)
    envelope = json.loads(queued.read_text(encoding="utf-8"))
    assert envelope["tenant_id"] == _TENANT_B, envelope
    assert envelope["field_id"] == "field-unit", envelope


def test_a_bound_detection_without_a_tenant_assertion_is_returned_not_synced(monkeypatch, tmp_path):
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(module, "get_pest_detector", lambda _bundle: _StubDetector())
    client = TestClient(module.app)
    response = _pest(client, _HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["sync_status"] == "not_synced_no_tenant", response.json()
    assert response.json()["detections"], "the detection itself is still returned"
    assert _queued(tmp_path) == [], "nothing may be queued for an unverified tenant"


def test_a_wrong_or_foreign_tenant_assertion_is_refused(monkeypatch, tmp_path):
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(module, "get_pest_detector", lambda _bundle: _StubDetector())
    client = TestClient(module.app)
    wrong_key = _pest(client, _signed("/v1/inference/pest-detect", key="x" * 40))
    assert wrong_key.status_code == 403, wrong_key.text
    other_route = _pest(client, _signed("/v1/inference/yield-estimate"))
    assert other_route.status_code == 403, other_route.text
    stranger = _pest(client, _signed("/v1/inference/pest-detect", service="raster"))
    assert stranger.status_code == 403, stranger.text
    forged = {**_signed("/v1/inference/pest-detect"), "X-Tenant-Id": "someone-else"}
    assert _pest(client, forged).status_code == 403, "tenant header swapped after signing"
    assert _queued(tmp_path) == [], "a refused request queued a result"


def test_missing_device_identity_returns_the_detection_instead_of_503(monkeypatch, tmp_path):
    """W0-08: inference ran; an unset EDGE_DEVICE_ID used to turn it into a 503 and drop it."""
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.delenv("EDGE_DEVICE_ID")
    monkeypatch.setattr(module, "get_pest_detector", lambda _bundle: _StubDetector())
    client = TestClient(module.app)
    response = _pest(client, _signed("/v1/inference/pest-detect"))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["sync_status"] == "not_synced_identity", payload
    assert payload["detections"][0]["class_name"] == "aphid", payload
    assert _queued(tmp_path) == [], "an observation without a device identity was queued"


class _FakeOnnxSession:
    """A synthetic ONNX head with valid input metadata and deterministic output."""

    def __init__(self, n_classes, *, yield_kg_ha=None, score=0.95):
        self.n_classes = n_classes
        self.yield_kg_ha = yield_kg_ha
        self.score = score

    def get_inputs(self):
        dimensions = [1, 3, 640, 640] if self.yield_kg_ha is None else [1, 6]
        return [SimpleNamespace(name="input", type="tensor(float)", shape=dimensions)]

    def get_outputs(self):
        shape = [1, 4 + self.n_classes, 64] if self.yield_kg_ha is None else [1, 1]
        return [SimpleNamespace(name="output", type="tensor(float)", shape=shape)]

    def run(self, _names, feeds):
        import numpy as np

        assert feeds["input"].dtype == np.float32
        assert list(feeds["input"].shape) == self.get_inputs()[0].shape
        if self.yield_kg_ha is not None:
            return [np.array([[self.yield_kg_ha]], dtype=np.float32)]
        out = np.zeros(self.get_outputs()[0].shape, dtype=np.float32)
        out[0, :4, 0] = (320, 320, 40, 40)
        out[0, 4, 0] = self.score
        return [out]


def _manifest_len() -> int:
    doc = json.loads((EDGE / "models_manifest" / "pest_labels.json").read_text(encoding="utf-8"))
    return len(doc["labels"])


def test_a_model_wider_than_its_label_manifest_is_a_503_not_a_mislabelled_pest(
    monkeypatch, tmp_path
):
    """W1-19 (scout-9): 11 classes against a 10-label manifest used to be truncated."""
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    from models import model_bundle

    monkeypatch.setattr(
        model_bundle,
        "open_session",
        lambda _weights, _device: _FakeOnnxSession(_manifest_len() + 1),
    )
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/pest-detect",
        files={"file": ("a.png", io.BytesIO(_png(8, 8)), "image/png")},
        headers=_HEADERS,
    )
    assert response.status_code == 503, f"mismatched model answered: {response.text}"
    detail = response.json()["detail"]
    assert detail["reason"] == "pest_model_label_contract_violation", f"{detail}"


def test_a_model_matching_its_label_manifest_detects_with_a_taxonomy_code(monkeypatch, tmp_path):
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/pest-detect",
        files={"file": ("a.png", io.BytesIO(_png(8, 8)), "image/png")},
        headers=_HEADERS,
    )
    assert response.status_code == 200, f"matching model refused: {response.text}"
    [detection] = response.json()["detections"]
    assert detection["class_name"] == "aphid", f"{detection}"
    assert detection["taxonomy_code"] == "aphid", f"{detection}"


def _replace(path, content):
    staged = path.with_suffix(".next")
    staged.write_bytes(content)
    staged.replace(path)


def _pest_bundle(tmp_path, weights, *, reversed_labels=False):
    doc = json.loads((EDGE / "models_manifest" / "pest_labels.json").read_bytes())
    if reversed_labels:
        doc["labels"].reverse()
        for index, item in enumerate(doc["labels"]):
            item["index"] = index
    labels = json.dumps(doc).encode()
    _replace(tmp_path / "weights.onnx", weights)
    _replace(tmp_path / "labels.json", labels)
    return {
        "weights": "weights.onnx",
        "weights_sha256": hashlib.sha256(weights).hexdigest(),
        "labels": "labels.json",
        "labels_sha256": hashlib.sha256(labels).hexdigest(),
        "preprocessing": "rgb640-chw-f32-v1",
    }


def _real_pest(client, *, headers=_HEADERS, data=None):
    return client.post(
        "/v1/inference/pest-detect",
        data=data,
        files={"file": ("a.png", io.BytesIO(_png(8, 8)), "image/png")},
        headers=headers,
    )


def test_in_flight_detection_keeps_its_session_labels_and_provenance_at_bundle_switch(
    monkeypatch, tmp_path
):
    from starlette.datastructures import UploadFile

    module = _load_edge(monkeypatch, tmp_path, approve=True)
    from models import model_bundle

    manifest = tmp_path / "bundle.json"
    a = _pest_bundle(tmp_path, b"model A")
    _replace(manifest, json.dumps(a).encode())
    monkeypatch.setenv("PEST_MODEL_BUNDLE_MANIFEST", str(manifest))
    loaded = []

    def open_session(weights, _device):
        loaded.append(weights)
        return _FakeOnnxSession(_manifest_len(), score=0.95 if weights == b"model A" else 0.85)

    monkeypatch.setattr(model_bundle, "open_session", open_session)
    original = UploadFile.read
    b = None

    async def switch_while_reading(upload, size=-1):
        nonlocal b
        if b is None:
            assert loaded == [b"model A"]
            b = _pest_bundle(tmp_path, b"model B", reversed_labels=True)
            _replace(manifest, json.dumps(b).encode())
        return await original(upload, size)

    monkeypatch.setattr(UploadFile, "read", switch_while_reading)
    client = TestClient(module.app)
    first = _real_pest(client)
    second = _real_pest(client)
    repeated = _real_pest(client)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert repeated.status_code == 200, repeated.text
    assert first.json()["detections"][0]["taxonomy_code"] == "aphid"
    assert second.json()["detections"][0]["taxonomy_code"] == "coffee_leaf_rust"
    assert first.json()["detections"][0]["confidence"] == pytest.approx(0.95)
    assert second.json()["detections"][0]["confidence"] == pytest.approx(0.85)
    assert first.json()["provenance"]["artifact_sha256"] == a["weights_sha256"]
    assert second.json()["provenance"]["artifact_sha256"] == b["weights_sha256"]
    assert (
        first.json()["provenance"]["bundle_sha256"] != second.json()["provenance"]["bundle_sha256"]
    )
    assert repeated.json()["provenance"] == second.json()["provenance"]
    assert loaded == [b"model A", b"model B"]


def test_yield_inference_keeps_its_verified_session_across_upload_and_rotation(
    monkeypatch, tmp_path
):
    from starlette.datastructures import UploadFile

    module = _load_edge(monkeypatch, tmp_path, approve=True)
    from models import model_bundle

    manifest = tmp_path / "yield-bundle.json"
    monkeypatch.setenv("YIELD_MODEL_BUNDLE_MANIFEST", str(manifest))

    def publish(weights):
        digest = hashlib.sha256(weights).hexdigest()
        _replace(tmp_path / "yield.onnx", weights)
        _replace(
            manifest,
            json.dumps(
                {
                    "weights": "yield.onnx",
                    "weights_sha256": digest,
                    "preprocessing": "rgb224-yield-features-v1",
                }
            ).encode(),
        )
        return digest

    original_sha = publish(b"yield A")
    monkeypatch.setattr(
        model_bundle,
        "open_session",
        lambda weights, _device: _FakeOnnxSession(
            0, yield_kg_ha=2500.0 if weights == b"yield A" else 2800.0
        ),
    )
    original_read = UploadFile.read
    next_sha = None

    async def rotate(upload, size=-1):
        nonlocal next_sha
        if next_sha is None:
            next_sha = publish(b"yield B")
        return await original_read(upload, size)

    monkeypatch.setattr(UploadFile, "read", rotate)
    client = TestClient(module.app)

    def estimate():
        result = client.post(
            "/v1/inference/yield-estimate",
            files=[("files", ("crop.png", io.BytesIO(_png(8, 8)), "image/png"))],
            data={"field_id": "field-unit", "image_count": "1"},
            headers=_HEADERS,
        )
        assert result.status_code == 200, result.text
        return result.json()

    first = estimate()
    second = estimate()
    assert first["estimated_yield_kg_ha"] == 2500.0
    assert second["estimated_yield_kg_ha"] == 2800.0
    assert first["model_artifact_sha256"] == original_sha
    assert second["model_artifact_sha256"] == next_sha
    assert first["model_bundle_sha256"] != second["model_bundle_sha256"]


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"labels_sha256": "0" * 64}, "pest_label_sha256_mismatch"),
        ({"preprocessing": "rgb-unsupported"}, "model_preprocessing_unsupported"),
        ({"weights": "../weights.onnx"}, "model_bundle_manifest_invalid"),
    ],
)
def test_invalid_pest_bundle_blocks_readiness_and_inference(monkeypatch, tmp_path, change, reason):
    monkeypatch.setenv("EDGE_READINESS_MODE", "strict")
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    manifest = tmp_path / "bundle.json"
    candidate = _pest_bundle(tmp_path, b"pest-model")
    _replace(manifest, json.dumps({**candidate, **change}).encode())
    monkeypatch.setenv("PEST_MODEL_BUNDLE_MANIFEST", str(manifest))

    client = TestClient(module.app)
    ready = client.get("/readyz")
    result = _real_pest(client)
    assert ready.status_code == 503, ready.text
    assert ready.json()["capabilities"]["pest_detect"]["reason"] == reason
    assert result.status_code == 503, result.text
    assert result.json()["detail"]["reason"] == reason
