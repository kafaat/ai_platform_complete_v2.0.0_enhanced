# SAHOOL v9 GPU images — build-only path (Docker Buildx Bake).
#
# Why this file exists: `docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml
# --profile gpu build` interpolates the WHOLE Compose model before it builds anything, so every
# runtime secret written as `${VAR:?...}` in any service (about 57 of them) must be set just to
# build two images. Compose also stops at the first missing one. Bake reads only this file, so
# the GPU images build with no runtime secrets and no `.env`.
#
# Usage (repository root):
#   docker buildx bake -f docker-bake.gpu.hcl                       # both GPU images
#   docker buildx bake -f docker-bake.gpu.hcl sahool-edge           # one image
#   docker buildx bake -f docker-bake.gpu.hcl --print               # resolved definition, no build
#
# Each target mirrors the build definition Compose produces for the same service from
# docker-compose.v9.yml + docker-compose.v9.gpu.yml (context, dockerfile, args and their
# defaults). tests_v9/test_gpu_bake_matches_compose_overlay.py fails when the two drift.
#
# Variables follow the overlay's `${VAR:-default}` rule: an unset OR empty value takes the
# default. Bake reads them from the shell environment (not from `.env`).
#
# Images are tagged `<COMPOSE_PROJECT_NAME>-<service>`, the name Compose gives a built service
# that has no `image:`. Use the same COMPOSE_PROJECT_NAME for Compose (`-p` or the variable) and
# `docker compose ... up --no-build` then runs these images instead of rebuilding them.

variable "COMPOSE_PROJECT_NAME" {
  default = "sahool"
}

variable "PIP_INDEX_URL" {
  default = ""
}

variable "PYTORCH_CUDA_IMAGE" {
  default = ""
}

group "default" {
  targets = ["sahool-edge", "sahool-sam2-inference"]
}

target "sahool-edge" {
  context    = "."
  dockerfile = "services/edge-inference/Dockerfile.arm64"
  args = {
    PIP_INDEX_URL     = PIP_INDEX_URL != "" ? PIP_INDEX_URL : "https://mirrors.aliyun.com/pypi/simple/"
    EDGE_REQUIREMENTS = "requirements-gpu.txt"
  }
  tags   = ["${COMPOSE_PROJECT_NAME}-sahool-edge"]
  output = ["type=docker"]
}

target "sahool-sam2-inference" {
  context    = "."
  dockerfile = "services/sam2-inference/Dockerfile"
  args = {
    PIP_INDEX_URL      = PIP_INDEX_URL != "" ? PIP_INDEX_URL : "https://mirrors.aliyun.com/pypi/simple/"
    PYTORCH_CUDA_IMAGE = PYTORCH_CUDA_IMAGE != "" ? PYTORCH_CUDA_IMAGE : "pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime"
  }
  tags   = ["${COMPOSE_PROJECT_NAME}-sahool-sam2-inference"]
  output = ["type=docker"]
}
