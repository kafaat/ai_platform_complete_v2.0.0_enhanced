"""SAHOOL Cookbook — نشر النماذج محليّاً (Ollama / vLLM / ONNX Runtime).

تبني كل دالّة قائمة الوسائط وتُشغّلها عبر subprocess بدون shell=True.
يمكن حقن دالّة تشغيل بديلة (runner) للاختبارات.

لا ترفع أيّ استثناء على كود خروج غير صفريّ — تُرجع ``ok=False`` بدلاً.
"""

from __future__ import annotations

import subprocess

# ──────────────────────────────────────────────────────────────────────────────
# دالّة التشغيل القابلة للحقن
# ──────────────────────────────────────────────────────────────────────────────


def _run(cmd: list[str]) -> tuple[int, str, str]:
    """تشغيل أمر خارجي وإرجاع (returncode, stdout, stderr).

    Args:
        cmd: قائمة الوسائط — بدون shell=True (أمان).

    Returns:
        ``(returncode, stdout, stderr)`` كـ tuple.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError as exc:
        return 1, "", f"الأمر غير موجود: {exc}"
    except Exception as exc:  # noqa: BLE001
        return 1, "", str(exc)


# ──────────────────────────────────────────────────────────────────────────────
# نشر عبر Ollama
# ──────────────────────────────────────────────────────────────────────────────


def deploy_ollama(
    model_name: str,
    quant: str,
    runner: object = _run,
) -> dict:
    """سحب نموذج من Ollama والتحقّق من وجوده في القائمة.

    Args:
        model_name: اسم النموذج (مثال: ``"qwen2.5-7b"``).
        quant: رمز التكميم (مثال: ``"Q4_K_M"``).
        runner: دالّة تشغيل بديلة للاختبارات.
                Signature: ``(cmd: list[str]) -> tuple[int, str, str]``.

    Returns:
        ``{"ok": bool, "cmd": list[str], "stdout": str, "stderr": str}``
    """
    pull_cmd = ["ollama", "pull", f"{model_name}:{quant}"]
    code, stdout, stderr = runner(pull_cmd)  # type: ignore[call-arg]

    if code != 0:
        return {"ok": False, "cmd": pull_cmd, "stdout": stdout, "stderr": stderr}

    # التحقّق من الوجود في القائمة
    list_cmd = ["ollama", "list"]
    _lc, list_out, list_err = runner(list_cmd)  # type: ignore[call-arg]

    tag = f"{model_name}:{quant}"
    found = tag.lower() in list_out.lower()

    return {
        "ok": found,
        "cmd": pull_cmd,
        "stdout": stdout + "\n" + list_out,
        "stderr": stderr + "\n" + list_err,
    }


# ──────────────────────────────────────────────────────────────────────────────
# نشر عبر vLLM
# ──────────────────────────────────────────────────────────────────────────────


def deploy_vllm(
    model_path: str,
    port: int = 8000,
    runner: object = _run,
) -> dict:
    """تشغيل خادم vLLM للنموذج المحدَّد.

    Args:
        model_path: مسار النموذج أو معرِّفه (HuggingFace Hub).
        port: منفذ الاستماع (افتراضيّاً 8000).
        runner: دالّة تشغيل بديلة للاختبارات.

    Returns:
        ``{"ok": bool, "cmd": list[str], "stdout": str, "stderr": str}``
    """
    cmd = [
        "vllm",
        "serve",
        model_path,
        "--port",
        str(port),
        "--max-model-len",
        "4096",
    ]
    code, stdout, stderr = runner(cmd)  # type: ignore[call-arg]
    return {"ok": code == 0, "cmd": cmd, "stdout": stdout, "stderr": stderr}


# ──────────────────────────────────────────────────────────────────────────────
# نشر عبر ONNX Runtime Server
# ──────────────────────────────────────────────────────────────────────────────


def deploy_onnx(
    model_path: str,
    port: int = 8080,
    runner: object = _run,
) -> dict:
    """تشغيل خادم ONNX Runtime للنموذج المحدَّد.

    Args:
        model_path: مسار ملف النموذج (``.onnx``).
        port: منفذ الاستماع (افتراضيّاً 8080).
        runner: دالّة تشغيل بديلة للاختبارات.

    Returns:
        ``{"ok": bool, "cmd": list[str], "stdout": str, "stderr": str}``
    """
    cmd = [
        "python",
        "-m",
        "onnxruntime_server",
        "--model",
        model_path,
        "--port",
        str(port),
    ]
    code, stdout, stderr = runner(cmd)  # type: ignore[call-arg]
    return {"ok": code == 0, "cmd": cmd, "stdout": stdout, "stderr": stderr}


__all__ = ["deploy_ollama", "deploy_onnx", "deploy_vllm"]
