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
        data={"field_id": "field-unit"},
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
        lambda: _StubEstimator(error=ValueError("yield_features_missing")),
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
        lambda: _StubEstimator(
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
    monkeypatch.setattr(module, "get_pest_detector", lambda: _StubDetector())
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
    monkeypatch.setattr(module, "get_pest_detector", lambda: _StubDetector())
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
    monkeypatch.setattr(module, "get_pest_detector", lambda: _DecodingDetector())
    monkeypatch.setattr(
        module,
        "get_yield_estimator",
        lambda: _DecodingEstimator(prediction={"yield_kg_ha": 1.0}),
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
    monkeypatch.setattr(module, "get_pest_detector", lambda: _StubDetector())
    monkeypatch.setattr(
        module, "get_yield_estimator", lambda: _StubEstimator(prediction={"yield_kg_ha": 1.0})
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
    import json

    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(module, "get_pest_detector", lambda: _StubDetector())
    image = b"\xff\xd8\xff-leaf"
    client = TestClient(module.app)
    response = client.post(
        "/v1/inference/pest-detect",
        data={"field_id": "field-unit", "confidence_threshold": "0.7"},
        files={"file": ("leaf.jpg", io.BytesIO(image), "image/jpeg")},
        headers=_signed("/v1/inference/pest-detect"),
    )
    assert response.status_code == 200
    gate_sha = module._model_capability("PEST_MODEL_PATH", "pest_detector_int8.onnx")[
        "actual_sha256"
    ]
    assert gate_sha == hashlib.sha256(b"pest-bytes").hexdigest()
    [queued] = _queued(tmp_path)
    provenance = json.loads(queued.read_text(encoding="utf-8"))["data"]["provenance"]
    assert provenance["artifact_sha256"] == gate_sha
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
    import json

    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(module, "get_pest_detector", lambda: _StubDetector())
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
    monkeypatch.setattr(module, "get_pest_detector", lambda: _StubDetector())
    client = TestClient(module.app)
    response = _pest(client, _HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["sync_status"] == "not_synced_no_tenant", response.json()
    assert response.json()["detections"], "the detection itself is still returned"
    assert _queued(tmp_path) == [], "nothing may be queued for an unverified tenant"


def test_a_wrong_or_foreign_tenant_assertion_is_refused(monkeypatch, tmp_path):
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    monkeypatch.setattr(module, "get_pest_detector", lambda: _StubDetector())
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
    monkeypatch.setattr(module, "get_pest_detector", lambda: _StubDetector())
    client = TestClient(module.app)
    response = _pest(client, _signed("/v1/inference/pest-detect"))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["sync_status"] == "not_synced_identity", payload
    assert payload["detections"][0]["class_name"] == "aphid", payload
    assert _queued(tmp_path) == [], "an observation without a device identity was queued"


class _FakeOnnxSession:
    """An inference session whose head has ``n_classes`` score rows (W1-19)."""

    def __init__(self, n_classes: int):
        self._n = n_classes

    def get_inputs(self):
        class _Input:
            name = "images"

        return [_Input()]

    def run(self, _names, _feeds):
        import numpy as np

        out = np.zeros((1, 4 + self._n, 64), dtype=np.float32)
        out[0, :4, 0] = (320, 320, 40, 40)
        out[0, 4, 0] = 0.95
        return [out]


def _detector_with_head(monkeypatch, n_classes: int):
    from models import pest_detector

    monkeypatch.setattr(
        pest_detector, "_load_onnx_session", lambda _p, _d: _FakeOnnxSession(n_classes)
    )
    return pest_detector.EdgePestDetector(model_path="/nonexistent/pest.onnx")


def _manifest_len() -> int:
    import json

    doc = json.loads((EDGE / "models_manifest" / "pest_labels.json").read_text(encoding="utf-8"))
    return len(doc["labels"])


def test_a_model_wider_than_its_label_manifest_is_a_503_not_a_mislabelled_pest(
    monkeypatch, tmp_path
):
    """W1-19 (scout-9): 11 classes against a 10-label manifest used to be truncated."""
    module = _load_edge(monkeypatch, tmp_path, approve=True)
    detector = _detector_with_head(monkeypatch, _manifest_len() + 1)
    monkeypatch.setattr(module, "get_pest_detector", lambda: detector)
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
    detector = _detector_with_head(monkeypatch, _manifest_len())
    monkeypatch.setattr(module, "get_pest_detector", lambda: detector)
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
