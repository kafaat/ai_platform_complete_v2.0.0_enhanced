"""SAHOOL Cookbook — اكتشاف العتاد (hardware detection) لبيئات Linux.

يكشف وحدات معالجة الرسوميّات (NVIDIA) والذاكرة العشوائيّة وأنوية المعالج
ثم يُرجع ملفّاً موحّداً يصف قدرات التشغيل المحليّة.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# مسار الذاكرة المؤقّتة
# ──────────────────────────────────────────────────────────────────────────────
_CACHE_PATH = Path("/tmp/sahool_hw_cache.json")
_CACHE_TTL_SEC = 86400  # 24 ساعة


def _run(cmd: list[str]) -> tuple[int, str, str]:
    """تشغيل أمر خارجي وإرجاع (رمز الخروج، stdout، stderr).

    Args:
        cmd: قائمة الوسائط (بدون shell=True لأسباب أمنيّة).

    Returns:
        Tuple of (returncode, stdout, stderr).
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        raise
    except Exception as exc:  # noqa: BLE001
        return 1, "", str(exc)


# ──────────────────────────────────────────────────────────────────────────────
# اكتشاف NVIDIA GPU
# ──────────────────────────────────────────────────────────────────────────────


def detect_nvidia(runner: Any = None) -> dict | None:
    """اكتشاف بطاقات الرسوميّات NVIDIA عبر nvidia-smi.

    Args:
        runner: دالّة بديلة لـ_run (لأغراض الاختبار فقط). Signature:
                ``(cmd: list[str]) -> tuple[int, str, str]``.

    Returns:
        قاموس يحوي ``gpu_name``, ``gpu_vram_gb``, ``gpu_count``, ``backend``
        أو ``None`` إذا لم تُكتشف بطاقة صالحة.
    """
    _runner = runner if runner is not None else _run
    cmd = [
        "nvidia-smi",
        "--query-gpu=memory.total,name",
        "--format=csv,noheader,nounits",
    ]
    try:
        code, stdout, _stderr = _runner(cmd)
    except FileNotFoundError:
        return None  # nvidia-smi غير مثبّت

    if code != 0 or not stdout.strip():
        return None  # خطأ في المشغّل أو لا توجد بطاقة

    gpus: list[dict] = []
    for line in stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            vram_mb = float(parts[0])
            name = parts[1]
            gpus.append({"name": name, "vram_mb": vram_mb})
        except ValueError:
            continue

    if not gpus:
        return None

    total_vram_gb = sum(g["vram_mb"] for g in gpus) / 1024.0
    primary_name = gpus[0]["name"]

    return {
        "gpu_name": primary_name,
        "gpu_vram_gb": round(total_vram_gb, 2),
        "gpu_count": len(gpus),
        "backend": "cuda",
    }


# ──────────────────────────────────────────────────────────────────────────────
# اكتشاف الذاكرة العشوائيّة والمعالج
# ──────────────────────────────────────────────────────────────────────────────


def detect_cpu_ram(
    meminfo_path: str = "/proc/meminfo",
    cpuinfo_path: str = "/proc/cpuinfo",
) -> dict:
    """قراءة معلومات المعالج والذاكرة من /proc.

    Args:
        meminfo_path: مسار ملف معلومات الذاكرة (قابل للتجاوز في الاختبارات).
        cpuinfo_path: مسار ملف معلومات المعالج (قابل للتجاوز في الاختبارات).

    Returns:
        قاموس يحوي ``total_ram_gb``, ``available_ram_gb``, ``cpu_cores``,
        ``cpu_name``.
    """
    total_kb = 0
    available_kb = 0

    try:
        with open(meminfo_path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available_kb = int(line.split()[1])
    except (OSError, ValueError):
        pass  # نعود إلى القيم الافتراضيّة

    cpu_name = "Unknown CPU"
    cpu_cores = os.cpu_count() or 1

    try:
        with open(cpuinfo_path, encoding="utf-8") as fh:
            logical_cores = 0
            for line in fh:
                if line.startswith("model name") and cpu_name == "Unknown CPU":
                    cpu_name = line.split(":", 1)[1].strip()
                if line.startswith("processor"):
                    logical_cores += 1
        if logical_cores > 0:
            cpu_cores = logical_cores
    except OSError:
        pass  # نكتفي بـos.cpu_count()

    return {
        "total_ram_gb": round(total_kb / (1024**2), 2),
        "available_ram_gb": round(available_kb / (1024**2), 2),
        "cpu_cores": cpu_cores,
        "cpu_name": cpu_name,
    }


# ──────────────────────────────────────────────────────────────────────────────
# الملف الموحّد
# ──────────────────────────────────────────────────────────────────────────────


def detect_platform(use_cache: bool = True) -> dict:
    """اكتشاف العتاد الكامل ودمجه في ملف موحّد.

    يدعم تخزيناً مؤقّتاً مدّته 24 ساعة في ``/tmp/sahool_hw_cache.json``.

    Args:
        use_cache: إذا كان True يُحاوَل قراءة الذاكرة المؤقّتة أوّلاً.

    Returns:
        قاموس موحّد يحوي معلومات GPU (إن وُجدت) + CPU + RAM + ``backend``.
    """
    if use_cache:
        cached = _read_cache()
        if cached is not None:
            return cached

    gpu_info = detect_nvidia()
    cpu_ram = detect_cpu_ram()

    if gpu_info is not None:
        backend = "cuda"
    elif platform.machine().lower() in ("aarch64", "arm64"):
        backend = "cpu_arm"
    else:
        backend = "cpu_x86"

    profile: dict = {"backend": backend}
    if gpu_info is not None:
        profile.update(gpu_info)
    profile.update(cpu_ram)

    if use_cache:
        _write_cache(profile)

    return profile


def clear_cache() -> None:
    """حذف الذاكرة المؤقّتة للعتاد."""
    try:
        _CACHE_PATH.unlink(missing_ok=True)
    except OSError:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# مساعدات الذاكرة المؤقّتة (خاصّة)
# ──────────────────────────────────────────────────────────────────────────────


def _read_cache() -> dict | None:
    """قراءة الذاكرة المؤقّتة إذا كانت صالحة (أقل من 24 ساعة)."""
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        ts = data.get("_ts", 0)
        if time.time() - ts < _CACHE_TTL_SEC:
            data.pop("_ts", None)
            return data
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        pass
    return None


def _write_cache(profile: dict) -> None:
    """كتابة الملف الموحّد في الذاكرة المؤقّتة مع طابع زمني."""
    try:
        payload = dict(profile)
        payload["_ts"] = time.time()
        _CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # لا نرفع استثناءً إذا تعذّر الحفظ


# ──────────────────────────────────────────────────────────────────────────────
# واجهة كائنيّة اختياريّة
# ──────────────────────────────────────────────────────────────────────────────


class HardwareProfiler:
    """غلاف خفيف حول دوال الاكتشاف.

    Example::

        profiler = HardwareProfiler()
        profile = profiler.profile()
        print(profile["backend"])
    """

    def __init__(self, use_cache: bool = True) -> None:
        """تهيئة الكاشف.

        Args:
            use_cache: استخدام الذاكرة المؤقّتة (24 ساعة).
        """
        self.use_cache = use_cache
        self._profile: dict | None = None

    def profile(self) -> dict:
        """إرجاع الملف الموحّد (مخزّن في الكائن بعد أوّل استدعاء).

        Returns:
            قاموس وصف العتاد الكامل.
        """
        if self._profile is None:
            self._profile = detect_platform(use_cache=self.use_cache)
        return self._profile

    def refresh(self) -> dict:
        """إعادة الاكتشاف متجاهلاً الذاكرة المؤقّتة.

        Returns:
            قاموس وصف العتاد المحدَّث.
        """
        self._profile = detect_platform(use_cache=False)
        return self._profile

    @staticmethod
    def clear_cache() -> None:
        """حذف الذاكرة المؤقّتة على القرص."""
        clear_cache()
