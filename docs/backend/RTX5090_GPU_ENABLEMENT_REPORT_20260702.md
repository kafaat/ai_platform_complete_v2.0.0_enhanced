# SAHOOL v9 RTX 5090 / GPU Enablement Report — 2026-07-02

## Scope

This patch enables the v9 runtime to use a local RTX 5090/Blackwell GPU without breaking the CPU/base deployment. The base stack remains `docker-compose.v9.yml`; GPU-specific behavior is isolated in `docker-compose.v9.gpu.yml`.

## Implemented changes

### 1. Added ZLMediaKit runtime to v9

`docker-compose.v9.yml` now includes `sahool-zlmediakit`, with local host ports for media development/testing:

- `127.0.0.1:8088:80` — ZLMediaKit HTTP/API
- `127.0.0.1:8554:554` — RTSP
- `127.0.0.1:1935:1935` — RTMP
- `127.0.0.1:10000:10000/udp` — WebRTC/RTP candidate port

`video-processor` now depends on `sahool-zlmediakit` and uses:

```text
ZLMEDIA_API_URL=http://sahool-zlmediakit:80
ZLMEDIAKIT_API_SECRET=${ZLMEDIAKIT_API_SECRET:-sahool-zlm-dev-secret}
```

### 2. Strengthened `video-processor` readiness

`video-processor` now exposes dependency status in `/readyz`:

- `zlmediakit`
- `edge_inference`

It supports strict fail-closed readiness through:

```text
VIDEO_STRICT_READY=true
```

The GPU overlay enables strict readiness for runtime smoke testing.

### 3. Fixed internal TTS wiring for notification-agent

`notification-agent` now has:

```text
TTS_URL=http://sahool-tts-service:8000
SAHOOL_AGENT_TOKEN=${SAHOOL_AGENT_TOKEN:-}
```

and depends on `sahool-tts-service` health. This closes the internal voice-notification drift where the code defaulted to `http://sahool-tts:8000`.

### 4. Added RTX 5090 GPU overlay

New file:

```text
docker-compose.v9.gpu.yml
```

It enables GPU reservations and NVIDIA runtime env for:

- `sahool-edge`
- `sahool-sam2-inference`
- `sahool-video-processor`

It also activates SAM2 field segmentation:

```text
SEGMENTATION_BACKEND=sam2
SEGMENTATION_INFERENCE_URL=http://sahool-sam2-inference:8080/predict
```

### 5. Made SAM2 Dockerfile RTX 50-ready by default

`services/sam2-inference/Dockerfile` now uses an overridable CUDA/PyTorch base:

```dockerfile
ARG PYTORCH_CUDA_IMAGE=pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime
FROM ${PYTORCH_CUDA_IMAGE}
```

This is intended for RTX 5090 / Blackwell support while allowing controlled image updates.

### 6. Made edge-inference recognize RTX/GPU device modes

`services/edge-inference/models/pest_detector.py` now enables CUDA providers when:

```text
EDGE_DEVICE in {jetson_orin, cuda, gpu, rtx5090, blackwell}
```

### 7. Added static and live GPU gates

Static gate:

```text
scripts/ci/v9_gpu_contract_gate.py
```

Live runtime gates for the local GPU server:

```text
scripts/e2e/gpu_runtime_smoke_gate.py
scripts/e2e/sam2_live_gpu_gate.py
scripts/e2e/video_zlmediakit_live_gate.py
```

### 8. CI integration

`.github/workflows/ci.yml` now runs:

```text
python scripts/ci/v9_gpu_contract_gate.py
```

The compose validation job treats `docker-compose.v9.gpu.yml` as an overlay and validates it together with `docker-compose.v9.yml`.

## How to run on the RTX 5090 local server

First verify the host runtime:

```bash
python scripts/e2e/gpu_runtime_smoke_gate.py
```

Then boot v9 with the GPU overlay:

```bash
docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml --profile gpu up -d
```

Then run live gates:

```bash
python scripts/e2e/video_zlmediakit_live_gate.py
python scripts/e2e/sam2_live_gpu_gate.py
```

## Verification performed in this environment

Docker/GPU live execution was not available here, so the live GPU gates were added but not executed. Static verification passed:

```text
service-feature-ui-contract-gate: PASS (26/26)
nginx-compose-dns-gate: PASS
service-port-gate: PASS
runtime-contract-gate: PASS
v9-feature-transfer-gate: PASS
v9-gpu-contract-gate: PASS
focused pytest: 32 passed
production validation gate: passed
Python compile compiled=1626 failed=0
```

## Remaining runtime-only work

The following must be run on the local RTX 5090 server:

1. NVIDIA Container Toolkit verification.
2. CUDA 12.8 container `nvidia-smi` smoke.
3. PyTorch CUDA 12.8 smoke.
4. v9 GPU compose boot.
5. ZLMediaKit live API check.
6. SAM2 live readiness/predict check with real model weights mounted.
7. Video stream registration against a real RTSP camera or sample stream.
