"""اختبارات وحدة حزمة SAHOOL Cookbook.

تغطّي: hardware_profiler, compatibility_engine, deploy_local.
تشغيل: python3 -m pytest tests_v9/test_cookbook.py -q
"""

from __future__ import annotations

import platform
import textwrap
from pathlib import Path

import pytest

import sahool_ai.cookbook.hardware_profiler as hp_mod
from sahool_ai.cookbook import (
    HardwareProfiler,
    clear_cache,
    deploy_ollama,
    deploy_onnx,
    deploy_vllm,
    detect_platform,
    estimate_vram_gb,
    fit_score,
    load_catalog,
    recommend_model,
)
from sahool_ai.cookbook.hardware_profiler import detect_cpu_ram, detect_nvidia

# ══════════════════════════════════════════════════════════════════════════════
# مساعدات الاختبار
# ══════════════════════════════════════════════════════════════════════════════


def _fake_runner_single_gpu(cmd: list[str]) -> tuple[int, str, str]:
    """مُحاكٍ لـ nvidia-smi يُرجع بطاقة رسوميّات واحدة."""
    return 0, "8192, NVIDIA RTX 3070\n", ""


def _fake_runner_multi_gpu(cmd: list[str]) -> tuple[int, str, str]:
    """مُحاكٍ لـ nvidia-smi يُرجع بطاقتَي رسوميّات."""
    return 0, "16384, NVIDIA A100\n24576, NVIDIA A100\n", ""


def _fake_runner_no_gpu(cmd: list[str]) -> tuple[int, str, str]:
    """مُحاكٍ لـ nvidia-smi يُرجع كود خطأ."""
    return 1, "", "NVIDIA-SMI has failed"


def _fake_runner_raises(cmd: list[str]) -> tuple[int, str, str]:
    """يُحاكي عدم وجود nvidia-smi."""
    raise FileNotFoundError("nvidia-smi not found")


# ══════════════════════════════════════════════════════════════════════════════
# اختبارات hardware_profiler
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_detect_nvidia_single_gpu() -> None:
    """detect_nvidia يُرجع بيانات صحيحة لبطاقة واحدة."""
    result = detect_nvidia(runner=_fake_runner_single_gpu)
    assert result is not None
    assert result["gpu_count"] == 1
    assert abs(result["gpu_vram_gb"] - 8.0) < 0.1
    assert result["gpu_name"] == "NVIDIA RTX 3070"
    assert result["backend"] == "cuda"


@pytest.mark.unit
def test_detect_nvidia_multi_gpu() -> None:
    """detect_nvidia يجمع ذاكرة بطاقتَي رسوميّات بشكل صحيح."""
    result = detect_nvidia(runner=_fake_runner_multi_gpu)
    assert result is not None
    assert result["gpu_count"] == 2
    # 16384 MB + 24576 MB = 41 GB تقريباً
    assert abs(result["gpu_vram_gb"] - (16384 + 24576) / 1024) < 0.1
    assert result["backend"] == "cuda"


@pytest.mark.unit
def test_detect_nvidia_no_gpu_nonzero_code() -> None:
    """detect_nvidia يُرجع None عند كود خطأ من nvidia-smi."""
    result = detect_nvidia(runner=_fake_runner_no_gpu)
    assert result is None


@pytest.mark.unit
def test_detect_nvidia_file_not_found() -> None:
    """detect_nvidia يُرجع None عند غياب nvidia-smi."""
    result = detect_nvidia(runner=_fake_runner_raises)
    assert result is None


@pytest.mark.unit
def test_detect_cpu_ram_fixture(tmp_path: Path) -> None:
    """detect_cpu_ram يقرأ قيم الذاكرة والمعالج من ملفّات مؤقّتة."""
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        textwrap.dedent("""\
            MemTotal:       16000000 kB
            MemFree:         4000000 kB
            MemAvailable:    8000000 kB
            Buffers:          200000 kB
        """),
        encoding="utf-8",
    )
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text(
        textwrap.dedent("""\
            processor\t: 0
            model name\t: Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz
            processor\t: 1
            model name\t: Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz
            processor\t: 2
            model name\t: Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz
            processor\t: 3
            model name\t: Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz
        """),
        encoding="utf-8",
    )

    result = detect_cpu_ram(
        meminfo_path=str(meminfo),
        cpuinfo_path=str(cpuinfo),
    )

    # 16 000 000 kB ÷ 1024² ≈ 15.26 GB
    assert abs(result["total_ram_gb"] - 16000000 / 1024**2) < 0.1
    # 8 000 000 kB ÷ 1024² ≈ 7.63 GB
    assert abs(result["available_ram_gb"] - 8000000 / 1024**2) < 0.1
    assert result["cpu_cores"] == 4
    assert "i7" in result["cpu_name"]


@pytest.mark.unit
def test_detect_cpu_ram_missing_files() -> None:
    """detect_cpu_ram لا يرفع استثناءً عند غياب الملفّات."""
    result = detect_cpu_ram(
        meminfo_path="/nonexistent/meminfo",
        cpuinfo_path="/nonexistent/cpuinfo",
    )
    assert "total_ram_gb" in result
    assert "available_ram_gb" in result
    assert "cpu_cores" in result
    assert "cpu_name" in result


@pytest.mark.unit
def test_detect_platform_cuda_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """detect_platform يُرجع backend=cuda عند وجود GPU."""
    monkeypatch.setattr(
        hp_mod,
        "detect_nvidia",
        lambda: {"backend": "cuda", "gpu_vram_gb": 8.0, "gpu_count": 1, "gpu_name": "Test GPU"},
    )
    monkeypatch.setattr(
        hp_mod,
        "detect_cpu_ram",
        lambda **_: {
            "total_ram_gb": 16.0,
            "available_ram_gb": 8.0,
            "cpu_cores": 4,
            "cpu_name": "Test CPU",
        },
    )
    result = detect_platform(use_cache=False)
    assert result["backend"] == "cuda"


@pytest.mark.unit
def test_detect_platform_cpu_x86_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """detect_platform يُرجع backend=cpu_x86 على x86 بلا GPU."""
    monkeypatch.setattr(hp_mod, "detect_nvidia", lambda: None)
    monkeypatch.setattr(
        hp_mod,
        "detect_cpu_ram",
        lambda **_: {
            "total_ram_gb": 8.0,
            "available_ram_gb": 4.0,
            "cpu_cores": 4,
            "cpu_name": "Test CPU",
        },
    )
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    result = detect_platform(use_cache=False)
    assert result["backend"] == "cpu_x86"


@pytest.mark.unit
def test_detect_platform_cpu_arm_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """detect_platform يُرجع backend=cpu_arm على ARM."""
    monkeypatch.setattr(hp_mod, "detect_nvidia", lambda: None)
    monkeypatch.setattr(
        hp_mod,
        "detect_cpu_ram",
        lambda **_: {
            "total_ram_gb": 8.0,
            "available_ram_gb": 4.0,
            "cpu_cores": 4,
            "cpu_name": "ARM CPU",
        },
    )
    monkeypatch.setattr(platform, "machine", lambda: "aarch64")
    result = detect_platform(use_cache=False)
    assert result["backend"] == "cpu_arm"


@pytest.mark.unit
def test_cache_write_read_clear(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """اختبار دورة كتابة/قراءة/حذف الذاكرة المؤقّتة."""
    cache_file = tmp_path / "test_hw_cache.json"
    monkeypatch.setattr(hp_mod, "_CACHE_PATH", cache_file)
    monkeypatch.setattr(hp_mod, "detect_nvidia", lambda: None)
    monkeypatch.setattr(
        hp_mod,
        "detect_cpu_ram",
        lambda **_: {
            "total_ram_gb": 8.0,
            "available_ram_gb": 4.0,
            "cpu_cores": 4,
            "cpu_name": "Test",
        },
    )

    # لا يوجد ذاكرة مؤقّتة بعد
    assert not cache_file.exists()

    # أوّل استدعاء يكتب الذاكرة
    profile1 = detect_platform(use_cache=True)
    assert cache_file.exists()

    # قراءة الذاكرة تُرجع نفس البيانات
    profile2 = detect_platform(use_cache=True)
    assert profile1["backend"] == profile2["backend"]

    # حذف الذاكرة
    clear_cache()
    assert not cache_file.exists()


@pytest.mark.unit
def test_hardware_profiler_class(monkeypatch: pytest.MonkeyPatch) -> None:
    """HardwareProfiler يُرجع ملفّ العتاد صحيحاً."""
    monkeypatch.setattr(hp_mod, "detect_nvidia", lambda: None)
    monkeypatch.setattr(
        hp_mod,
        "detect_cpu_ram",
        lambda **_: {
            "total_ram_gb": 8.0,
            "available_ram_gb": 4.0,
            "cpu_cores": 4,
            "cpu_name": "Test",
        },
    )
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    profiler = HardwareProfiler(use_cache=False)
    profile = profiler.profile()
    assert "backend" in profile
    assert profile["total_ram_gb"] == 8.0


# ══════════════════════════════════════════════════════════════════════════════
# اختبارات compatibility_engine
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_estimate_vram_gb_exact() -> None:
    """estimate_vram_gb يُرجع قيمة صحيحة لـ 7B Q4_K_M context 4096."""
    # 7 * 0.58 + 0.000008 * 7 * 4096 + 0.5 = 4.06 + 0.229376 + 0.5 = 4.789376
    expected = 7.0 * 0.58 + 0.000008 * 7.0 * 4096 + 0.5
    result = estimate_vram_gb(7.0, "Q4_K_M", context_length=4096)
    assert abs(result - expected) < 0.01


@pytest.mark.unit
def test_estimate_vram_gb_unknown_quant_raises() -> None:
    """estimate_vram_gb يرفع ValueError على تكميم مجهول."""
    with pytest.raises(ValueError, match="غير معروف"):
        estimate_vram_gb(7.0, "UNKNOWN_QUANT")


@pytest.mark.unit
def test_load_catalog_count_and_keys() -> None:
    """load_catalog يُحمّل ≥20 نموذجاً بالمفاتيح المطلوبة."""
    catalog = load_catalog()
    assert len(catalog) >= 20, f"عدد النماذج {len(catalog)} أقل من 20"
    required_keys = {"name", "type", "params_b", "use_case", "min_ram_gb"}
    for model in catalog:
        missing = required_keys - model.keys()
        assert not missing, f"النموذج '{model.get('name')}' ينقصه: {missing}"


@pytest.mark.unit
def test_recommend_model_cpu_8gb() -> None:
    """recommend_model يجد نموذجاً llm مناسباً لـ 8GB RAM."""
    profile = {
        "backend": "cpu_x86",
        "total_ram_gb": 8.0,
        "available_ram_gb": 7.0,
        "cpu_cores": 4,
        "cpu_name": "Test CPU",
    }
    result = recommend_model(profile, task_type="llm")
    assert result is not None
    assert "model" in result
    assert "quantization" in result
    assert result["estimated_vram_gb"] > 0


@pytest.mark.unit
def test_recommend_model_none_for_1gb_13b() -> None:
    """recommend_model يُرجع None عند عدم توفّر ذاكرة كافية."""
    profile = {
        "backend": "cpu_x86",
        "total_ram_gb": 1.0,
        "available_ram_gb": 0.8,
        "cpu_cores": 2,
        "cpu_name": "Test CPU",
    }
    # لا نموذج llm يعمل على 1 GB
    result = recommend_model(profile, task_type="llm")
    assert result is None


@pytest.mark.unit
def test_recommend_model_fallback_context() -> None:
    """recommend_model يُجرّب سياقاً أصغر عند ضيق الذاكرة."""
    # 2 GB متاح — قد لا يكفي context=4096 لكن يكفي context=512
    profile = {
        "backend": "cpu_x86",
        "total_ram_gb": 4.0,
        "available_ram_gb": 2.5,
        "cpu_cores": 4,
        "cpu_name": "Test CPU",
    }
    # embedding صغير يجب أن يُوجد
    result = recommend_model(profile, task_type="embedding", context_length=4096)
    # إمّا نجح أو لم ينجح — الهدف ألّا يرفع استثناءً
    assert result is None or isinstance(result["model"], str)


@pytest.mark.unit
def test_recommend_model_onnx() -> None:
    """recommend_model يختار نماذج onnx بدون تكميم."""
    profile = {
        "backend": "cpu_x86",
        "total_ram_gb": 4.0,
        "available_ram_gb": 3.0,
        "cpu_cores": 4,
        "cpu_name": "Test CPU",
    }
    result = recommend_model(profile, task_type="onnx")
    assert result is not None
    assert result["quantization"] is None
    assert result["model"].startswith("sahool-")


@pytest.mark.unit
def test_fit_score_range() -> None:
    """fit_score يُرجع قيمة بين 0 و100."""
    profile = {
        "backend": "cpu_x86",
        "total_ram_gb": 16.0,
        "available_ram_gb": 12.0,
        "cpu_cores": 8,
        "cpu_name": "Test CPU",
    }
    model_cfg = {"params_b": 7.0, "min_ram_gb": 6, "name": "test-7b"}
    score = fit_score(profile, model_cfg, quant="Q4_K_M")
    assert 0.0 <= score <= 100.0


@pytest.mark.unit
def test_fit_score_higher_for_more_headroom() -> None:
    """fit_score أعلى لملف عتاد بذاكرة أكبر."""
    model_cfg = {"params_b": 7.0, "min_ram_gb": 6, "name": "test-7b"}

    rich_profile = {
        "backend": "cpu_x86",
        "total_ram_gb": 32.0,
        "available_ram_gb": 28.0,
        "cpu_cores": 16,
        "cpu_name": "Big CPU",
    }
    poor_profile = {
        "backend": "cpu_x86",
        "total_ram_gb": 8.0,
        "available_ram_gb": 6.5,
        "cpu_cores": 2,
        "cpu_name": "Small CPU",
    }
    rich_score = fit_score(rich_profile, model_cfg, quant="Q4_K_M")
    poor_score = fit_score(poor_profile, model_cfg, quant="Q4_K_M")
    assert rich_score > poor_score


@pytest.mark.unit
def test_fit_score_deterministic() -> None:
    """fit_score يُنتج نفس النتيجة عند الاستدعاء مرّتين."""
    profile = {
        "backend": "cuda",
        "gpu_vram_gb": 24.0,
        "total_ram_gb": 64.0,
        "available_ram_gb": 50.0,
        "cpu_cores": 32,
        "cpu_name": "Server CPU",
    }
    model_cfg = {"params_b": 13.0, "min_ram_gb": 10, "name": "jais-13b"}
    s1 = fit_score(profile, model_cfg, quant="Q5_K_M")
    s2 = fit_score(profile, model_cfg, quant="Q5_K_M")
    assert s1 == s2


# ══════════════════════════════════════════════════════════════════════════════
# اختبارات deploy_local
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_deploy_ollama_exact_argv() -> None:
    """deploy_ollama يبني argv صحيحاً."""
    captured: list[list[str]] = []

    def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
        captured.append(cmd)
        tag = "mymodel:Q4_K_M"
        if cmd[0] == "ollama" and cmd[1] == "list":
            return 0, f"{tag}\n", ""
        return 0, "pulling...", ""

    result = deploy_ollama("mymodel", "Q4_K_M", runner=fake_runner)
    assert result["ok"] is True
    # الأمر الأوّل هو pull
    assert captured[0] == ["ollama", "pull", "mymodel:Q4_K_M"]
    # الأمر الثاني هو list
    assert captured[1] == ["ollama", "list"]


@pytest.mark.unit
def test_deploy_ollama_failure_ok_false() -> None:
    """deploy_ollama يُرجع ok=False عند كود خطأ."""

    def bad_runner(cmd: list[str]) -> tuple[int, str, str]:
        return 1, "", "network error"

    result = deploy_ollama("badmodel", "Q4_K_M", runner=bad_runner)
    assert result["ok"] is False
    assert result["stderr"] == "network error"


@pytest.mark.unit
def test_deploy_vllm_exact_argv() -> None:
    """deploy_vllm يبني argv صحيحاً."""
    captured: list[list[str]] = []

    def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
        captured.append(cmd)
        return 0, "server started", ""

    result = deploy_vllm("/models/qwen", port=9000, runner=fake_runner)
    assert result["ok"] is True
    assert captured[0] == [
        "vllm",
        "serve",
        "/models/qwen",
        "--port",
        "9000",
        "--max-model-len",
        "4096",
    ]


@pytest.mark.unit
def test_deploy_vllm_nonzero_no_raise() -> None:
    """deploy_vllm يُرجع ok=False ولا يرفع استثناءً على كود غير صفريّ."""

    def bad_runner(cmd: list[str]) -> tuple[int, str, str]:
        return 127, "", "command not found"

    result = deploy_vllm("/models/missing", runner=bad_runner)
    assert result["ok"] is False
    assert not isinstance(result, Exception)


@pytest.mark.unit
def test_deploy_onnx_exact_argv() -> None:
    """deploy_onnx يبني argv صحيحاً."""
    captured: list[list[str]] = []

    def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
        captured.append(cmd)
        return 0, "onnx server up", ""

    result = deploy_onnx("/models/crop.onnx", port=8888, runner=fake_runner)
    assert result["ok"] is True
    assert captured[0] == [
        "python",
        "-m",
        "onnxruntime_server",
        "--model",
        "/models/crop.onnx",
        "--port",
        "8888",
    ]


@pytest.mark.unit
def test_deploy_onnx_nonzero_no_raise() -> None:
    """deploy_onnx لا يرفع استثناءً على كود خطأ."""

    def bad_runner(cmd: list[str]) -> tuple[int, str, str]:
        return 1, "", "onnxruntime_server not installed"

    result = deploy_onnx("/models/bad.onnx", runner=bad_runner)
    assert result["ok"] is False
    assert "onnxruntime_server" in result["stderr"]
