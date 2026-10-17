# SAM2 — official checkpoint identified, installation still unproved

The configured default is **SAM2 Hiera Large (July 2024)**,
`sam2_hiera_large.pt`, not SAM2.1 or `model.safetensors`.

Publisher sources:

- Meta download: https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_large.pt
- Official model repository, pinned revision: https://huggingface.co/facebook/sam2-hiera-large/tree/e6a8e8809b8f1bfa2238b6d080f3d05cc76bd251
- Published pointer: https://huggingface.co/facebook/sam2-hiera-large/raw/e6a8e8809b8f1bfa2238b6d080f3d05cc76bd251/sam2_hiera_large.pt

Published file SHA256:

```text
7442e4e9b732a508f80e141e7c2913437a3610ee0c77381a66658c3a445df87b
```

The publisher pointer is retained as `official-lfs-pointer.txt`. This is the
file SHA256, **not** the Xet object hash or the Git blob ID. Expected size:
897,952,466 bytes. An independent streaming download from Meta's URL returned
HTTP 200 and matched both size and SHA256; see
`official-weight-verification.json`. The bytes were hashed without Torch,
deserialization, installation or retention in the repository. Access succeeded;
there is no access blocker for this official object in this session.

## Existing provisioning and enforcement

1. `sam2-models/README.md:16-30` and `docs/SAM2_DEPLOYMENT.md:53-73` describe an
   operator download/copy into `sam2-models` or the model volume. The Dockerfile
   does not bake the checkpoint into the image.
2. `docker-compose.v9.yml:2632-2638` mounts `./sam2-models:/models:ro` and passes
   `SAM2_CHECKPOINT_SHA256`, whose default is empty. No Compose/env edit is made.
3. `services/sam2-inference/sam2_runtime.py:109` computes the file digest;
   `:151-160` refuses absent/invalid/mismatched expected digests before Torch
   loading. `build_sam2` is reached at `:183` only after verification.
4. Source code is already pinned in `services/sam2-inference/Dockerfile:43` to
   `2b90b9f5ceec907a1c18123530e92e794ad901a4`; no source pin change is needed here.

Reproduce the independent byte check without loading the model:

```bash
curl --fail --location \
  https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_large.pt \
  --output /tmp/sam2-hiera-large-reviewed.pt
printf '%s  %s\n' \
  7442e4e9b732a508f80e141e7c2913437a3610ee0c77381a66658c3a445df87b \
  /tmp/sam2-hiera-large-reviewed.pt | sha256sum --check -
```

Remaining: owner approval of this artifact for the intended deployment, a
provisioning receipt binding the actual installed bytes/path/image/config to
this digest, and runtime acceptance in the designated environment. A publisher
digest and a successful local byte check do not prove what is installed in
staging/production. The gap remains open; no configuration, model or deployment
has been changed and no verified status is assigned.
