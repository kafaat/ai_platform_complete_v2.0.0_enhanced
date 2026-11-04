#!/usr/bin/env python3
"""RTX 5090 / CUDA runtime smoke gate for the local server.

Run on the GPU host after installing NVIDIA Container Toolkit:
  python scripts/e2e/gpu_runtime_smoke_gate.py

After building the GPU profile, verify the edge image itself:
  python scripts/e2e/gpu_runtime_smoke_gate.py --edge

Set SAHOOL_SKIP_DOCKER_GPU_SMOKE=1 to only run host nvidia-smi.
"""

from __future__ import annotations

import argparse
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


def check_edge_gpu() -> None:
    # mul_1.onnx ships inside the ORT wheel. Disable CPU placement and run its sole Mul node.
    code = """
import numpy as np
import onnxruntime as ort
from onnxruntime.datasets import get_example

options = ort.SessionOptions()
options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
session = ort.InferenceSession(get_example("mul_1.onnx"), options, providers=["CUDAExecutionProvider"])
if "CUDAExecutionProvider" not in session.get_providers():
    raise SystemExit("edge ONNX session did not load CUDAExecutionProvider")
session.disable_fallback()
result, = session.run(None, {"X": np.ones((3, 2), dtype=np.float32)})
np.testing.assert_array_equal(result, np.arange(1, 7).reshape(3, 2))
print("edge CUDA Mul passed", ort.__version__, session.get_providers())
""".strip()
    run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.v9.yml",
            "-f",
            "docker-compose.v9.gpu.yml",
            "--profile",
            "gpu",
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "sahool-edge",
            "python",
            "-c",
            code,
        ],
        timeout=180,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge", action="store_true", help="test the built edge image on CUDA")
    args = parser.parse_args()
    if args.edge:
        check_edge_gpu()
        return 0

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
