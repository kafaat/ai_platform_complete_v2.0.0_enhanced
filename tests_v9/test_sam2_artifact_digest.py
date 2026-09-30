"""EDGE-MODEL-ARTIFACT-DIGEST-01 — SAM2 bytes must match approved SHA-256."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "services" / "sam2-inference" / "sam2_runtime.py"


def _load_runtime():
    spec = importlib.util.spec_from_file_location("_sam2_digest_runtime", RUNTIME)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_matching_checkpoint_digest_is_verified(tmp_path):
    rt = _load_runtime()
    model = tmp_path / "sam2.pt"
    model.write_bytes(b"approved-sam2-checkpoint")
    expected = hashlib.sha256(model.read_bytes()).hexdigest()

    verified, actual, reason = rt._verify_checkpoint_artifact(str(model), expected)

    assert verified is True
    assert actual == expected
    assert reason is None


def test_missing_or_invalid_checkpoint_digest_fails_closed_before_identity_claim(tmp_path):
    rt = _load_runtime()
    model = tmp_path / "sam2.pt"
    model.write_bytes(b"unidentified-checkpoint")

    for expected in ("", "abc", "g" * 64):
        verified, actual, reason = rt._verify_checkpoint_artifact(str(model), expected)
        assert verified is False
        assert actual is None
        assert reason == "checkpoint_digest_missing_or_invalid"


def test_mismatching_checkpoint_digest_names_the_actual_bytes(tmp_path):
    rt = _load_runtime()
    model = tmp_path / "sam2.pt"
    model.write_bytes(b"wrong-checkpoint")
    actual_expected = hashlib.sha256(model.read_bytes()).hexdigest()

    verified, actual, reason = rt._verify_checkpoint_artifact(str(model), "0" * 64)

    assert verified is False
    assert actual == actual_expected
    assert reason == "checkpoint_digest_mismatch"


def test_model_load_verifies_artifact_before_importing_torch(monkeypatch):
    rt = _load_runtime()
    calls = []

    def refuse(*_args):
        calls.append("verify")
        return False, None, "checkpoint_digest_missing_or_invalid"

    monkeypatch.setattr(rt, "_verify_checkpoint_artifact", refuse)
    monkeypatch.setitem(sys.modules, "torch", None)

    rt._load_model()

    assert calls == ["verify"]
    assert rt._PREDICTOR is None
    assert rt._MODEL_ARTIFACT_DIGEST is None
    assert rt._MODEL_LOAD_REASON_CODE == "checkpoint_digest_missing_or_invalid"


def _load_main(monkeypatch):
    svc = ROOT / "services" / "sam2-inference"
    monkeypatch.syspath_prepend(str(svc))
    sys.modules.pop("sam2_runtime", None)
    sys.modules.pop("_sam2_digest_main", None)
    spec = importlib.util.spec_from_file_location("_sam2_digest_main", svc / "main.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_readyz_surfaces_verified_artifact_digest(monkeypatch):
    import asyncio

    main = _load_main(monkeypatch)
    digest = "a" * 64
    main.rt._PREDICTOR = object()
    main.rt._MODEL_ARTIFACT_DIGEST = digest
    main.rt._MODEL_LOAD_ERROR = None
    main.rt._MODEL_LOAD_REASON_CODE = None

    body = asyncio.run(main.readyz())

    assert body["artifact_digest"] == digest
    assert body["artifact_digest_verified"] is True
    assert body["status"] == "ready"


def test_predict_metadata_surfaces_verified_artifact_digest(monkeypatch):
    import asyncio
    import contextlib

    import numpy as np

    main = _load_main(monkeypatch)
    digest = "b" * 64

    class Predictor:
        def set_image(self, _rgb):
            return None

        def predict(self, **_kwargs):
            return [np.ones((2, 2), dtype=np.uint8)], [0.9], None

    class TorchStub:
        bfloat16 = object()

        @staticmethod
        def inference_mode():
            return contextlib.nullcontext()

        @staticmethod
        def autocast(*_args, **_kwargs):
            return contextlib.nullcontext()

    main.rt.AGENT_TOKEN = "token"
    main.rt._PREDICTOR = Predictor()
    main.rt._MODEL_ARTIFACT_DIGEST = digest
    monkeypatch.setitem(sys.modules, "torch", TorchStub)
    monkeypatch.setattr(main.rt, "_resolve_image_url", lambda *_args: "memory://image")
    monkeypatch.setattr(
        main.rt,
        "_read_rgb",
        lambda *_args: (np.zeros((2, 2, 3), dtype=np.uint8), object(), None),
    )
    monkeypatch.setattr(
        main.rt,
        "_build_prompt",
        lambda *_args: (np.array([[0, 0]]), np.array([1]), None),
    )
    monkeypatch.setattr(
        main.rt,
        "_mask_to_polygon",
        lambda *_args: {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        },
    )

    req = main.rt.PredictRequest(mode="auto")
    body = asyncio.run(main.predict(req, x_agent_token="token"))

    assert body["metadata"]["artifact_digest"] == digest
    assert body["metadata"]["model"] == "sam2"


@pytest.mark.parametrize(
    "approved_digest,reason_code",
    [
        ("", "checkpoint_digest_missing_or_invalid"),  # .env.example وافتراضُ compose كما هما
        ("a" * 64, "weights_missing"),  # بصمةٌ معتمدة والأوزانُ غائبة
    ],
    ids=["env_example_digest_empty", "digest_set_weights_absent"],
)
def test_absent_weights_keep_the_process_up_and_answer_503_with_a_named_reason(
    monkeypatch, tmp_path, approved_digest, reason_code
):
    """الأوزانُ غائبة (آلةُ التدقيق الحيّ 2026-09-29): التطبيقُ الحقيقيّ بحدث إقلاعه.

    مقيسٌ 2026-09-30 بـTestClient: العمليّةُ لا تسقط (فلا حلقةَ إعادة تشغيل)، ``/healthz``
    200 — وهو ما يسأله فحصُ Docker في v9 عمداً (حياةٌ لا جاهزيّة) — و``/readyz`` 503
    بسببٍ مسمًّى، و``/v1/predict`` 503 ``model_not_loaded`` بلا هندسةٍ مختلَقة.
    """
    from fastapi.testclient import TestClient

    token = "t" * 40
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", token)
    monkeypatch.setenv("SAM2_CHECKPOINT", str(tmp_path / "sam2_hiera_large.pt"))
    monkeypatch.setenv("SAM2_CHECKPOINT_SHA256", approved_digest)
    main = _load_main(monkeypatch)

    with TestClient(main.app) as client:  # يُشغِّل حدثَ الإقلاع ⇒ _load_model()
        alive = client.get("/healthz")
        ready = client.get("/readyz")
        predict = client.post(
            "/v1/predict",
            json={"mode": "auto", "field_bbox": [44.1, 15.3, 44.2, 15.4]},
            headers={"X-Agent-Token": token},
        )

    assert alive.status_code == 200
    assert ready.status_code == 503
    body = ready.json()
    assert (body["status"], body["model_loaded"]) == ("degraded", False)
    assert body["reason_code"] == reason_code
    assert body["artifact_digest_verified"] is False
    assert predict.status_code == 503
    assert predict.json()["detail"]["error"] == "model_not_loaded"
    assert "geometry" not in predict.json()


def test_every_documented_sam2_compose_surface_wires_checkpoint_digest():
    for rel in ("docker-compose.v9.yml", "docker-compose.fixed.yml"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "sahool-sam2-inference:" in text
        assert "SAM2_CHECKPOINT_SHA256: ${SAM2_CHECKPOINT_SHA256:-}" in text


def test_sam2_deployment_runbook_requires_digest_and_verifies_bytes():
    text = (ROOT / "docs" / "SAM2_DEPLOYMENT.md").read_text(encoding="utf-8")
    assert "SAM2_CHECKPOINT_SHA256=<64-hex-sha256>" in text
    assert "sha256sum -c -" in text
