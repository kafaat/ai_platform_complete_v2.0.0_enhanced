# SAHOOL v9 RTX 5090 / GPU Enablement Report — 2026-07-02

## Scope

This patch enables the v9 runtime to use a local RTX 5090/Blackwell GPU without breaking the CPU/base deployment. The base stack remains `docker-compose.v9.yml`; GPU-specific behavior is isolated in `docker-compose.v9.gpu.yml`.

## Implemented changes

### 1. Added ZLMediaKit runtime to v9

`docker-compose.v9.yml` now includes `sahool-zlmediakit`, with local host ports for media development/testing:

- `127.0.0.1:8188:80` — ZLMediaKit HTTP/API (moved from 8088 to avoid raster-tiler collision)
- `127.0.0.1:18554:554` — RTSP (moved from 8554 to avoid Android Emulator collision)
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

## Windows + WSL2 runbook (RTX 5090 Laptop / Blackwell `sm_120`)

Verified against a real host: `NVIDIA GeForce RTX 5090 Laptop`, 24 GB VRAM, Driver
`592.00`, CUDA `13.1`, driver model **WDDM** (Windows). The base CPU stack
(`docker-compose.v9.yml`) is unaffected; GPU behavior lives only in the overlay.

### 1. Start the Linux engine

Open Docker Desktop on Windows, select Linux containers and enable **Use the WSL 2
based engine** under Settings → General. Update WSL with `wsl --update` if needed.
Install the WSL-compatible NVIDIA driver on Windows. Docker Desktop manages the
engine in its own distribution. Running Docker commands from PowerShell does not
require installing Ubuntu or configuring a separate Docker daemon inside it.
[Docker Desktop WSL 2 setup](https://docs.docker.com/desktop/features/wsl/)

```powershell
docker context ls
docker info --format '{{.OSType}}'
```

Continue when the second command succeeds and prints `linux`. A missing
`dockerDesktopLinuxEngine` pipe indicates that the CLI could not reach its selected
engine. Start Docker Desktop from the Start menu or run `docker desktop start`,
wait for readiness and repeat the check. If the active context is unexpected, check
the terminal's `DOCKER_CONTEXT` and `DOCKER_HOST` overrides.

### 2. Verify GPU passthrough before running the services

```powershell
docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi
```

The GPU should appear in the container output. A registry or image-pull failure
must be resolved before the command can test the device.
[Docker Desktop GPU requirements and validation](https://docs.docker.com/desktop/features/gpu/)

### 3. Build and start the GPU stack

Prepare the required local settings in `.env` and provision the checkpoint
described in [the SAM2 setup instructions](../../sam2-models/README.md).
From a clean Git checkout, use the following block in PowerShell. Compose needs
the same build identifiers when it reads the files again for startup.

```powershell
$previousSha = $env:TESTED_SHA
$previousId = $env:SAHOOL_BUILD_ID
try {
    $env:TESTED_SHA = git rev-parse HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve Git commit.' }
    if ([string]::IsNullOrWhiteSpace($previousId)) {
        $env:SAHOOL_BUILD_ID = "local-$($env:TESTED_SHA.Substring(0,12))"
    }
    .\scripts\build-immutable.ps1 -Gpu
    python scripts/e2e/gpu_runtime_smoke_gate.py --edge
    if ($LASTEXITCODE -ne 0) { throw 'CUDA inference failed in the built edge image.' }
    docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml --profile gpu up -d --no-build
    if ($LASTEXITCODE -ne 0) { throw 'GPU stack startup failed.' }
} finally {
    $env:TESTED_SHA = $previousSha
    $env:SAHOOL_BUILD_ID = $previousId
}
```
This activates SAM2 (`SEGMENTATION_BACKEND=sam2`), GPU reservations for
`sahool-edge` / `sahool-sam2-inference` / `sahool-video-processor`, and strict
video readiness (`VIDEO_STRICT_READY=true`).

### 4. Prove it works (live gates — run on the GPU host, not in CI)
```bash
python scripts/e2e/gpu_runtime_smoke_gate.py      # CUDA visibility and PyTorch GPU matmul
python scripts/e2e/sam2_live_gpu_gate.py          # SAM2 field-segmentation end-to-end
python scripts/e2e/video_zlmediakit_live_gate.py  # ZLMediaKit + video-processor /readyz
```

### Compatibility notes for this exact card
- **Driver 13.1 ⊃ runtime 12.8:** a newer driver runs the SAM2 image's CUDA 12.8
  runtime fine — no action needed. To move to a CUDA 13.x runtime later, override
  `PYTORCH_CUDA_IMAGE=pytorch/pytorch:<cu13-tag>` (the Dockerfile arg is already there).
- **Blackwell `sm_120`:** `TORCH_CUDA_ARCH_LIST=12.0` matches; `pytorch:2.7.0-cuda12.8`
  ships `sm_120` kernels, so no build-from-source is required.
- **24 GB VRAM (laptop):** ample for SAM2 (~4–8 GB) + edge inference. `count: all` +
  `NVIDIA_VISIBLE_DEVICES=all` are correct for a single-GPU box.
- **150 W cap / WDDM:** inference-only workloads run comfortably; WDDM is the only mode
  on a consumer laptop GPU and WSL2 supports it.

## تحديث 2026-07-07 — تحقّق التوافق (سائق CUDA 13.1) + تشخيص جاهزيّة SAM2

**توافق CUDA 13.1 / سائق 592 مع صورة cuda12.8:** سائق NVIDIA بدرجة CUDA 13.1 **متوافق خلفيّاً**
مع حاويات CUDA 12.8 (السائق الأحدث يشغّل runtime أقدم). لذا `PYTORCH_CUDA_IMAGE` الافتراضيّة
`pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime` صحيحة لـRTX 5090: PyTorch 2.7 + cu12.8 يدعم
Blackwell **sm_120** (`TORCH_CUDA_ARCH_LIST=12.0`). **لا حاجة لصورة cuda13** — ومتى توفّرت رسميّاً
تُمرَّر عبر `PYTORCH_CUDA_IMAGE` (قابلة للتجاوز أصلاً).

**تشخيص جاهزيّة SAM2 (صادق قابل للتنفيذ):** `GET /readyz` يُصنّف سبب عدم التحميل صراحةً:
- `reason_code: weights_missing` + `checkpoint_expected` — **حالتك الحاليّة** (GPU جاهز، الأوزان غير
  مركّبة). الحلّ: ضع `sam2_hiera_large.pt` على مسار `SAM2_CHECKPOINT` (volume `sam2-models` → `/models`).
- `cuda_unavailable` / `library_missing` / `load_failed` — تشخيص بقيّة الحالات دون قراءة السجلّات.
التحقّق الحيّ للعتاد يبقى عبر `scripts/e2e/sam2_live_gpu_gate.py` على الجهاز (لا يمكن هنا: لا GPU).
