#!/usr/bin/env python3
"""Static contract gate for SAHOOL v9 RTX 5090/GPU enablement.

This gate is intentionally static: it does not require a GPU or Docker. It locks the
repository wiring that must be present before runtime GPU smoke tests are attempted.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def fail(msg: str) -> None:
    print(f"v9-gpu-contract-gate: FAIL: {msg}")
    sys.exit(1)


def load_yaml(rel: str) -> dict:
    p = ROOT / rel
    if not p.exists():
        fail(f"missing {rel}")
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def env_of(service: dict) -> dict:
    env = service.get("environment") or {}
    if isinstance(env, list):
        out = {}
        for item in env:
            if "=" in item:
                k, v = item.split("=", 1)
                out[k] = v
        return out
    return env


def main() -> int:
    base = load_yaml("docker-compose.v9.yml")
    gpu = load_yaml("docker-compose.v9.gpu.yml")
    services = base.get("services") or {}
    gpu_services = gpu.get("services") or {}

    for name in [
        "sahool-zlmediakit",
        "sahool-video-processor",
        "sahool-edge",
        "sahool-sam2-inference",
        "sahool-field-segmentation",
        "sahool-tts-service",
        "sahool-notification-agent",
    ]:
        if name not in services:
            fail(f"docker-compose.v9.yml missing service {name}")

    zlm = services["sahool-zlmediakit"]
    if not zlm.get("image"):
        fail("sahool-zlmediakit must use an explicit image")
    if "healthcheck" not in zlm:
        fail("sahool-zlmediakit must have a healthcheck")

    video = services["sahool-video-processor"]
    video_env = env_of(video)
    if "sahool-zlmediakit" not in str(video_env.get("ZLMEDIA_API_URL", "")):
        fail("video-processor ZLMEDIA_API_URL must point at sahool-zlmediakit")
    if "sahool-zlmediakit" not in (video.get("depends_on") or {}):
        fail("video-processor must depend_on sahool-zlmediakit")
    if "ZLMEDIAKIT_API_SECRET" not in video_env:
        fail("video-processor must receive ZLMEDIAKIT_API_SECRET")

    notif_env = env_of(services["sahool-notification-agent"])
    if notif_env.get("TTS_URL") != "http://sahool-tts-service:8000":
        fail("notification-agent TTS_URL must point at sahool-tts-service")
    if "sahool-tts-service" not in (services["sahool-notification-agent"].get("depends_on") or {}):
        fail("notification-agent must depend_on sahool-tts-service")

    for name in ["sahool-edge", "sahool-sam2-inference", "sahool-video-processor"]:
        if name not in gpu_services:
            fail(f"docker-compose.v9.gpu.yml missing GPU override for {name}")
        if "devices" not in str(gpu_services[name].get("deploy", {})):
            fail(f"{name} GPU override must reserve NVIDIA device")

    seg_env = env_of(gpu_services.get("sahool-field-segmentation", {}))
    if seg_env.get("SEGMENTATION_BACKEND") != "sam2":
        fail("GPU overlay must set SEGMENTATION_BACKEND=sam2")
    if seg_env.get("SEGMENTATION_INFERENCE_URL") != "http://sahool-sam2-inference:8080/predict":
        fail("GPU overlay must wire field-segmentation to sam2-inference")

    sam2_dockerfile = (ROOT / "services/sam2-inference/Dockerfile").read_text(encoding="utf-8")
    if "cuda12.8" not in sam2_dockerfile or "PYTORCH_CUDA_IMAGE" not in sam2_dockerfile:
        fail("sam2 Dockerfile must default to a CUDA 12.8 PyTorch image and be overridable")

    pest_detector = (ROOT / "services/edge-inference/models/pest_detector.py").read_text(
        encoding="utf-8"
    )
    if "rtx5090" not in pest_detector or "CUDAExecutionProvider" not in pest_detector:
        fail("edge pest detector must recognize rtx5090/cuda device for CUDAExecutionProvider")

    for rel in [
        "scripts/e2e/gpu_runtime_smoke_gate.py",
        "scripts/e2e/sam2_live_gpu_gate.py",
        "scripts/e2e/video_zlmediakit_live_gate.py",
    ]:
        if not (ROOT / rel).exists():
            fail(f"missing runtime smoke script {rel}")

    print("v9-gpu-contract-gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
