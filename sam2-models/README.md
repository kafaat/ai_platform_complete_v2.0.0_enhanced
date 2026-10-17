# SAM2 model weights (`sam2-models/`)

This folder is **bind-mounted read-only** into the `sahool-sam2-inference` container at
`/models` (`docker-compose.v9.yml` → `./sam2-models:/models:ro`). Put the SAM2 checkpoint
here on the GPU host; the container reads it via `SAM2_CHECKPOINT` (default
`/models/sam2_hiera_large.pt`).

> The weights are large (~900 MB) and are **not** committed — see `.gitignore`.

## Provision the default Hiera Large checkpoint

Run from the repository root on the GPU host (Python 3, including Windows):

```bash
python scripts/ops/provision_sam2_checkpoint.py --output-dir sam2-models
python scripts/ops/provision_sam2_checkpoint.py --output-dir sam2-models --check
```

This downloads **SAM2 Hiera Large (July 2024)** from Meta into a temporary file.
Only a complete file matching the pinned publisher SHA256 and size is moved into
`sam2-models/sam2_hiera_large.pt`. A wrong, truncated or interrupted download
leaves an existing checkpoint untouched. The command prints a JSON receipt;
retain it with your deployment evidence. It never loads Torch or starts services.

Configure the existing runtime check with the same independently measured pin:

```dotenv
SAM2_CHECKPOINT=/models/sam2_hiera_large.pt
SAM2_CHECKPOINT_SHA256=7442e4e9b732a508f80e141e7c2913437a3610ee0c77381a66658c3a445df87b
SAM2_MODEL_CFG=sam2_hiera_l.yaml
```

[Official source and independent byte measurement](../certification/evidence/chatgpt_w5_20261017/sam2/README.md).
The provisioner has no URL/hash override: a different checkpoint requires a
separately reviewed source, digest and compatible configuration. SAM2.1, smaller
variants and safetensors are not covered by this receipt.

## Verify

After placing the file and bringing up the GPU stack:
```bash
docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml --profile gpu up -d
# The runtime independently hashes the mounted checkpoint before importing Torch:
curl -fsS http://localhost:8000/readyz   # inside the container / via the gateway
python scripts/e2e/sam2_live_gpu_gate.py  # end-to-end GPU inference probe
```

If the checkpoint is missing, `sahool-sam2-inference` still starts but `/readyz` reports the
weights-missing error and `SEGMENTATION_BACKEND=sam2` field-segmentation returns an honest
"model not ready" instead of fabricating a mask.
