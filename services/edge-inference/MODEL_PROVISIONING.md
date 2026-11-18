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
and the two inference endpoints verify the mounted bytes against the configured SHA-256.
Readiness additionally requires an initialized ONNX session with compatible inputs, outputs and
label contract. In strict mode, a failed activation returns 503 from readiness. The approved
model record must separately pin model/version, license, class taxonomy, training-data provenance
and regional calibration evidence **before** a digest is set — the digest proves identity, not fitness.

**Class index -> label comes from a label manifest** (W1-19).
`models_manifest/pest_labels.json` lists, by class index, the label each pest-model class means
and its canonical code in `shared/agronomy/pest_taxonomy.py`. A model whose output width is not
`4 + len(labels)`, or a missing/invalid manifest, is refused with a 503
(`pest_model_label_contract_violation`); it is never truncated to the shorter list. A model with
a different class list ships its own manifest. In static configuration, set `PEST_LABELS_PATH`
and `PEST_LABELS_SHA256` together. The default shipped dictionary has a repository-pinned digest.

### In-process bundle rotation

Set `PEST_MODEL_BUNDLE_MANIFEST` and/or `YIELD_MODEL_BUNDLE_MANIFEST` to the path of an
operator-controlled JSON file. When configured, this file supplies the approved paths and hashes
for that model in place of its static environment configuration. Mount the approval file
read-only to the inference container. Grant write access only to the approved release process.

For Docker Compose, pass these variables to the container in an override file. A project
`.env` alone does not forward additional variables to `sahool-edge`.

```yaml
services:
  sahool-edge:
    environment:
      PEST_MODEL_BUNDLE_MANIFEST: /models/pest-approved.json
      YIELD_MODEL_BUNDLE_MANIFEST: /models/yield-approved.json
```

Pest manifest example

```json
{
  "weights": "pest-2026-11.onnx",
  "weights_sha256": "<approved 64-hex sha256>",
  "labels": "pest-labels-2026-11.json",
  "labels_sha256": "<approved 64-hex sha256>",
  "preprocessing": "rgb640-chw-f32-v1"
}
```

For yield, supply `weights`, `weights_sha256`, and `preprocessing` set to
`rgb224-yield-features-v1`. Serve standalone ONNX files with their tensors embedded.
Place versioned weights and labels next to the respective manifest, then atomically rename the
reviewed manifest into place. Each request holds its original bundle through completion. The
next request and readiness probe select the updated approval. An invalid replacement makes new
inference unavailable until a complete approved bundle is supplied. To roll back, republish the
prior manifest and keep its versioned files available.

`/capabilities` exposes the active bundle fingerprint, label fingerprint and preprocessing
profile. Pest provenance preserves the weights digest in `artifact_sha256` and carries
`bundle_sha256` in the Edge response and sync envelope. The platform's current persisted
detection provenance records the weights digest. Yield responses include both digests.

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
