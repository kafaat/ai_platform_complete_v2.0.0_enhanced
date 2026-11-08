"""اختيار مزوّد ONNX في edge-inference وذاكرة الجلسات المفصولة لكلّ مزوّد (#1347).

`onnx_providers(device)` صار التعريفَ الواحد لقائمة المزوّدين بدل نسختين في
`pest_detector` و`yield_estimator`، ومفتاحُ ذاكرة الجلسات صار (المسار، المزوّد الأوّل)
كي لا تُعيد جلسةُ CPU المخزّنة نفسَها لطلب CUDA على الملفّ ذاته (والعكس).

الوحداتُ تُحمَّل من شجرة الخدمة بـ`models` اسماً علويّاً كما في الصورة، ثمّ تُعاد
`sys.modules` إلى حالها كي لا يتسرّب اسم `models` إلى بقيّة جلسة pytest.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

EDGE = Path(__file__).resolve().parents[1] / "services" / "edge-inference"
GPU_DEVICES = ("jetson_orin", "cuda", "gpu", "rtx5090", "blackwell", "CUDA", "RTX5090")
CPU_DEVICES = ("rpi5", "cpu", "", "jetson_nano")


@pytest.fixture
def edge_models(monkeypatch):
    saved = {k: v for k, v in sys.modules.items() if k == "models" or k.startswith("models.")}
    for name in saved:
        del sys.modules[name]
    monkeypatch.syspath_prepend(str(EDGE))
    try:
        yield {
            "pkg": importlib.import_module("models"),
            "pest": importlib.import_module("models.pest_detector"),
            "yield": importlib.import_module("models.yield_estimator"),
        }
    finally:
        for name in [k for k in sys.modules if k == "models" or k.startswith("models.")]:
            del sys.modules[name]
        sys.modules.update(saved)


class _FakeSession:
    def __init__(self, path, providers):
        self.path = path
        self.providers = list(providers)


def _fake_ort(monkeypatch, *, fail: bool = False):
    created: list[_FakeSession] = []

    def inference_session(path, providers):
        if fail:
            raise RuntimeError("provider unavailable")
        session = _FakeSession(path, providers)
        created.append(session)
        return session

    monkeypatch.setitem(
        sys.modules, "onnxruntime", types.SimpleNamespace(InferenceSession=inference_session)
    )
    return created


@pytest.mark.parametrize("device", GPU_DEVICES)
def test_gpu_devices_prefer_cuda_and_keep_cpu_fallback(edge_models, device):
    assert edge_models["pkg"].onnx_providers(device) == [
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ]


@pytest.mark.parametrize("device", CPU_DEVICES)
def test_other_devices_use_cpu_only(edge_models, device):
    assert edge_models["pkg"].onnx_providers(device) == ["CPUExecutionProvider"]


@pytest.mark.parametrize("module", ["pest", "yield"])
def test_session_cache_is_keyed_by_model_path_and_provider(edge_models, monkeypatch, module):
    mod = edge_models[module]
    monkeypatch.setattr(mod, "_ONNX_SESSION_CACHE", {})
    created = _fake_ort(monkeypatch)

    cpu = mod._load_onnx_session("/models/m.onnx", "rpi5")
    gpu = mod._load_onnx_session("/models/m.onnx", "rtx5090")

    assert cpu is not gpu
    assert cpu.providers == ["CPUExecutionProvider"]
    assert gpu.providers == ["CUDAExecutionProvider", "CPUExecutionProvider"]
    assert set(mod._ONNX_SESSION_CACHE) == {
        ("/models/m.onnx", "CPUExecutionProvider"),
        ("/models/m.onnx", "CUDAExecutionProvider"),
    }
    # نفس المسار والمزوّد ⇒ الجلسة المخزّنة، بلا بناء جديد (cuda وrtx5090 يتشاركان المزوّد).
    assert mod._load_onnx_session("/models/m.onnx", "cuda") is gpu
    assert mod._load_onnx_session("/models/m.onnx", "cpu") is cpu
    assert len(created) == 2


@pytest.mark.parametrize("module", ["pest", "yield"])
def test_missing_onnxruntime_is_dormant(edge_models, monkeypatch, module):
    mod = edge_models[module]
    monkeypatch.setattr(mod, "_ONNX_SESSION_CACHE", {})
    monkeypatch.setitem(sys.modules, "onnxruntime", None)  # يجعل import يرفع ImportError
    assert mod._load_onnx_session("/models/m.onnx", "cuda") is None
    assert mod._ONNX_SESSION_CACHE == {}


@pytest.mark.parametrize("module", ["pest", "yield"])
def test_failed_session_is_dormant_and_not_cached(edge_models, monkeypatch, module):
    mod = edge_models[module]
    monkeypatch.setattr(mod, "_ONNX_SESSION_CACHE", {})
    _fake_ort(monkeypatch, fail=True)
    assert mod._load_onnx_session("/models/m.onnx", "cuda") is None
    assert mod._ONNX_SESSION_CACHE == {}
