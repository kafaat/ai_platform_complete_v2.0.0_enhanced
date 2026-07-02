#!/usr/bin/env python3
"""RTX 5090 / CUDA runtime smoke gate for the local server.

Run on the GPU host after installing NVIDIA Container Toolkit:
  python scripts/e2e/gpu_runtime_smoke_gate.py

Set SAHOOL_SKIP_DOCKER_GPU_SMOKE=1 to only run host nvidia-smi.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def run(cmd: list[str], timeout: int = 120) -> str:
    print("$", " ".join(cmd))
    p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    if p.stdout:
        print(p.stdout)
    if p.stderr:
        print(p.stderr, file=sys.stderr)
    if p.returncode != 0:
        raise SystemExit(p.returncode)
    return p.stdout


def main() -> int:
    if not shutil.which("nvidia-smi"):
        print("gpu-runtime-smoke: FAIL: nvidia-smi not found", file=sys.stderr)
        return 1
    out = run(["nvidia-smi"], timeout=30)
    if "NVIDIA-SMI" not in out:
        print("gpu-runtime-smoke: FAIL: unexpected nvidia-smi output", file=sys.stderr)
        return 1

    if os.getenv("SAHOOL_SKIP_DOCKER_GPU_SMOKE", "").lower() in {"1", "true", "yes"}:
        print("gpu-runtime-smoke: PASS host nvidia-smi only")
        return 0

    if not shutil.which("docker"):
        print("gpu-runtime-smoke: FAIL: docker not found", file=sys.stderr)
        return 1

    cuda_image = os.getenv("SAHOOL_CUDA_SMOKE_IMAGE", "nvidia/cuda:12.8.0-base-ubuntu24.04")
    run(["docker", "run", "--rm", "--gpus", "all", cuda_image, "nvidia-smi"], timeout=180)

    torch_image = os.getenv(
        "SAHOOL_TORCH_SMOKE_IMAGE", "pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime"
    )
    code = """
import torch
print('torch', torch.__version__)
print('cuda', torch.version.cuda)
print('available', torch.cuda.is_available())
print('device_count', torch.cuda.device_count())
if not torch.cuda.is_available():
    raise SystemExit('CUDA is not available inside PyTorch container')
print('device', torch.cuda.get_device_name(0))
x = torch.randn(2048, 2048, device='cuda')
y = x @ x
torch.cuda.synchronize()
print('matmul_ok', float(y[0, 0]))
""".strip()
    run(["docker", "run", "--rm", "--gpus", "all", torch_image, "python", "-c", code], timeout=300)
    print("gpu-runtime-smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
