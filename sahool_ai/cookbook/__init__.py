"""SAHOOL Cookbook — الواجهة البرمجيّة العامّة لحزمة التوصية بالنماذج.

تُعيد تصدير كل الدوال والكلاسات المطلوبة:

- :func:`detect_platform` / :class:`HardwareProfiler` — اكتشاف العتاد.
- :func:`estimate_vram_gb` — تقدير ذاكرة الرسوميّات المطلوبة.
- :func:`recommend_model` — اختيار أفضل نموذج+تكميم للعتاد الحالي.
- :func:`fit_score` — درجة توافق نموذج مع ملف عتاد.
- :func:`load_catalog` — تحميل كتالوج النماذج من YAML.
- :func:`deploy_ollama` / :func:`deploy_vllm` / :func:`deploy_onnx` — النشر.
- :func:`clear_cache` — حذف ذاكرة اكتشاف العتاد المؤقّتة.
"""

from __future__ import annotations

from sahool_ai.cookbook.compatibility_engine import (
    estimate_vram_gb,
    fit_score,
    load_catalog,
    recommend_model,
)
from sahool_ai.cookbook.deploy_local import deploy_ollama, deploy_onnx, deploy_vllm
from sahool_ai.cookbook.hardware_profiler import (
    HardwareProfiler,
    clear_cache,
    detect_platform,
)

__all__ = [
    "HardwareProfiler",
    "clear_cache",
    "deploy_onnx",
    "deploy_ollama",
    "deploy_vllm",
    "detect_platform",
    "estimate_vram_gb",
    "fit_score",
    "load_catalog",
    "recommend_model",
]
