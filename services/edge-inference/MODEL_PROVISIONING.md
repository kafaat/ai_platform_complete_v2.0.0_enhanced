# Edge Inference model provisioning

The edge-inference service is intentionally fail-closed. The repository does not ship pest or yield ONNX weights. Operators must mount the model volume at `/models` and provide:

- `/models/pest_detector_int8.onnx`
- `/models/yield_estimator_int8.onnx`

The service exposes `/capabilities` and `/readyz` so deployment automation can see whether those contracts are active.

Recommended production mode:

```env
EDGE_READINESS_MODE=strict
PEST_MODEL_PATH=/models/pest_detector_int8.onnx
YIELD_MODEL_PATH=/models/yield_estimator_int8.onnx
PEST_MODEL_SHA256=<64-hex sha256 of the approved pest weight>
YIELD_MODEL_SHA256=<64-hex sha256 of the approved yield weight>
```

**A file name never activates a capability.** `/capabilities`, `/readyz`, `download_models.py`
and the two inference endpoints all verify the mounted bytes against the configured SHA-256 and
stay fail-closed on a missing, malformed or mismatched digest (`reason` names which). The approved
model record must separately pin model/version, license, class taxonomy, training-data provenance
and regional calibration evidence **before** a digest is set — the digest proves identity, not fitness.

**The detector is observation-only.** Detections carry class, confidence, bbox, affected crops and
severity, with `action_policy: observation_only`. No treatment or pesticide is emitted by the
detector; agronomic action requires a policy layer and an approved diagnosis.

Use `EDGE_READINESS_MODE=partial` only when Edge inference is optional and endpoint-level 503 responses are acceptable until models are provisioned.


## GPU profile and persistent volumes

The base image installs ONNX Runtime for CPU. The GPU overlay selects the CUDA 12
and cuDNN 9 wheel for Linux x86-64. Leave `EDGE_DEVICE` empty to use the profile's
default. In an existing `.env`, remove a stale `EDGE_DEVICE=rpi5` override before
running the RTX profile.

After building the GPU profile, run the following command from the repository root
on the Docker GPU host with the same Compose environment, including `TESTED_SHA`
and `SAHOOL_BUILD_ID`. The [Windows runbook](../../docs/backend/RTX5090_GPU_ENABLEMENT_REPORT_20260702.md#3-build-and-start-the-gpu-stack)
sets these for the build and the smoke test in one PowerShell session.
The test executes a multiplication on CUDA inside the built edge
image with CPU fallback disabled. The test uses the example model shipped by ONNX
Runtime and works before either agricultural model is provisioned.

```sh
python scripts/e2e/gpu_runtime_smoke_gate.py --edge
```

For existing named volumes, check access after rebuilding the service:

```sh
docker compose -f docker-compose.v9.yml run --rm --no-deps sahool-edge sh -c 'id && ls -ld /data/sync_queue /models && test -w /data/sync_queue'
```

If the existing sync queue is root-owned, stop the edge service and repair its
directory ownership before restarting it. This preserves queued JSON records:

```sh
docker compose -f docker-compose.v9.yml run --rm --no-deps --user root sahool-edge chown -R sahool:sahool /data/sync_queue
```
