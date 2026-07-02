# SAM2 model weights (`sam2-models/`)

This folder is **bind-mounted read-only** into the `sahool-sam2-inference` container at
`/models` (`docker-compose.v9.yml` → `./sam2-models:/models:ro`). Put the SAM2 checkpoint
here on the GPU host; the container reads it via `SAM2_CHECKPOINT` (default
`/models/sam2_hiera_large.pt`).

> The weights are large (~900 MB) and are **not** committed — see `.gitignore`. Only this
> README and `.gitkeep` are tracked.

## What to download (default = Hiera-Large)

The service defaults to the SAM2 Hiera-Large checkpoint + its config
(`SAM2_MODEL_CFG=sam2_hiera_l.yaml`, shipped inside the `sam2` pip package).

Download the checkpoint into this folder as `sam2_hiera_large.pt`:

```bash
# from the repo root, on the GPU host
cd sam2-models
curl -fL -o sam2_hiera_large.pt \
  https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_large.pt
# (SAM 2.1 alternative — update SAM2_CHECKPOINT/SAM2_MODEL_CFG accordingly:)
#   https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt
```

Windows PowerShell:
```powershell
cd sam2-models
Invoke-WebRequest -Uri "https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_large.pt" -OutFile "sam2_hiera_large.pt"
```

## Smaller variants (less VRAM / faster)

Override the two env vars (e.g. in `.env`) to use a smaller model:

| Model | Checkpoint file | `SAM2_MODEL_CFG` |
|---|---|---|
| Hiera-Large (default) | `sam2_hiera_large.pt` | `sam2_hiera_l.yaml` |
| Hiera-Base+ | `sam2_hiera_base_plus.pt` | `sam2_hiera_b+.yaml` |
| Hiera-Small | `sam2_hiera_small.pt` | `sam2_hiera_s.yaml` |
| Hiera-Tiny | `sam2_hiera_tiny.pt` | `sam2_hiera_t.yaml` |

```env
SAM2_CHECKPOINT=/models/sam2_hiera_small.pt
SAM2_MODEL_CFG=sam2_hiera_s.yaml
```

The RTX 5090 Laptop (24 GB) runs Hiera-Large comfortably; the smaller variants are for
lower-VRAM hosts or lower latency.

## Verify

After placing the file and bringing up the GPU stack:
```bash
docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml --profile gpu up -d
# the service checks os.path.isfile(SAM2_CHECKPOINT) on startup:
curl -fsS http://localhost:8000/readyz   # inside the container / via the gateway
python scripts/e2e/sam2_live_gpu_gate.py  # end-to-end GPU inference probe
```

If the checkpoint is missing, `sahool-sam2-inference` still starts but `/readyz` reports the
weights-missing error and `SEGMENTATION_BACKEND=sam2` field-segmentation returns an honest
"model not ready" instead of fabricating a mask.
