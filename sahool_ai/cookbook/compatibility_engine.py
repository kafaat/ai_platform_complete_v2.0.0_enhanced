"""SAHOOL Cookbook — محرّك التوافق بين النماذج والعتاد.

يحسب تقديرات ذاكرة الرسوميّات، ويوصي بأفضل نموذج+تكميم للعتاد المكتشف،
ويحسب درجة توافق قابلة للمقارنة (0-100).
"""

from __future__ import annotations

from pathlib import Path

import yaml

# ──────────────────────────────────────────────────────────────────────────────
# ثوابت التكميم (bits-per-parameter فعليّة، مُعامِل اصطلاحي)
# ──────────────────────────────────────────────────────────────────────────────

QUANT_BPP: dict[str, float] = {
    "F16": 2.0,
    "Q8_0": 1.05,
    "Q6_K": 0.80,
    "Q5_K_M": 0.68,
    "Q4_K_M": 0.58,
    "Q3_K_M": 0.48,
    "Q2_K": 0.37,
}

# ترتيب التكميم من الأعلى جودةً إلى الأدنى
QUALITY_ORDER: list[str] = ["Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "Q3_K_M", "Q2_K"]

# المسار الافتراضي للكتالوج (بجانب هذا الملف)
_DEFAULT_CATALOG = Path(__file__).parent / "model_catalog.yaml"


# ──────────────────────────────────────────────────────────────────────────────
# تحميل الكتالوج
# ──────────────────────────────────────────────────────────────────────────────


def load_catalog(path: str | None = None) -> list[dict]:
    """تحميل كتالوج النماذج من ملف YAML.

    Args:
        path: مسار ملف YAML. إذا كان ``None`` يُستخدم الكتالوج المُضمَّن.

    Returns:
        قائمة من القواميس، كل منها يمثّل نموذجاً في الكتالوج.

    Raises:
        FileNotFoundError: إذا لم يُوجد الملف المحدَّد.
        yaml.YAMLError: إذا كان الملف تالفاً.
    """
    catalog_path = Path(path) if path is not None else _DEFAULT_CATALOG
    with open(catalog_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("models", [])


# ──────────────────────────────────────────────────────────────────────────────
# تقدير ذاكرة الرسوميّات
# ──────────────────────────────────────────────────────────────────────────────


def estimate_vram_gb(
    params_b: float,
    quant: str,
    context_length: int = 4096,
) -> float:
    """تقدير حجم ذاكرة الرسوميّات (أو الذاكرة الرئيسيّة) المطلوبة.

    المعادلة::

        params_b × QUANT_BPP[quant] + 0.000008 × params_b × context_length + 0.5

    Args:
        params_b: عدد المعاملات بالمليار.
        quant: رمز التكميم (مثال: ``"Q4_K_M"``، ``"F16"``).
        context_length: طول السياق بالرموز (tokens).

    Returns:
        التقدير بالجيجابايت (float).

    Raises:
        ValueError: إذا كان رمز التكميم مجهولاً (مع رسالة عربيّة).
    """
    if quant not in QUANT_BPP:
        known = ", ".join(QUANT_BPP.keys())
        raise ValueError(f"رمز التكميم '{quant}' غير معروف. الرموز المدعومة: {known}")
    bpp = QUANT_BPP[quant]
    vram = params_b * bpp + 0.000008 * params_b * context_length + 0.5
    return round(vram, 4)


# ──────────────────────────────────────────────────────────────────────────────
# التوصية بالنموذج
# ──────────────────────────────────────────────────────────────────────────────


def _available_memory_gb(hardware_profile: dict) -> float:
    """استخراج الذاكرة المتاحة من ملف العتاد بحسب الخلفيّة.

    Args:
        hardware_profile: ملف العتاد الصادر من :func:`detect_platform`.

    Returns:
        الذاكرة المتاحة بالجيجابايت.
    """
    backend = hardware_profile.get("backend", "cpu_x86")
    if backend == "cuda":
        return float(hardware_profile.get("gpu_vram_gb", 0.0))
    return float(hardware_profile.get("available_ram_gb", 0.0))


def recommend_model(
    hardware_profile: dict,
    task_type: str,
    catalog: list[dict] | None = None,
    context_length: int = 4096,
) -> dict | None:
    """توصية بأفضل نموذج وتكميم يناسب العتاد والمهمّة.

    Args:
        hardware_profile: ملف العتاد (من :func:`detect_platform`).
        task_type: نوع النموذج المطلوب (``"llm"``, ``"embedding"``, ``"onnx"``).
        catalog: قائمة نماذج. إذا كانت ``None`` يُستخدم الكتالوج المُضمَّن.
        context_length: طول السياق المطلوب (tokens). يُجرَّب تصغيره تلقائيّاً.

    Returns:
        قاموس ``{model, quantization, estimated_vram_gb, confidence}``
        أو ``None`` إذا لم يُجد نموذج مناسب.
    """
    if catalog is None:
        catalog = load_catalog()

    # تصفية الكتالوج بحسب النوع والذاكرة الرئيسيّة
    total_ram_gb = float(hardware_profile.get("total_ram_gb", 0.0))
    candidates = [
        m
        for m in catalog
        if m.get("type") == task_type and float(m.get("min_ram_gb", 0)) <= total_ram_gb
    ]

    avail_mem = _available_memory_gb(hardware_profile)
    backend = hardware_profile.get("backend", "cpu_x86")

    # ترتيب البحث في التكميم: GPU يُفضّل الأعلى جودةً، CPU يُفضّل Q4_K_M
    if backend == "cuda":
        quant_order = ["F16"] + QUALITY_ORDER
    else:
        # نبدأ من Q4_K_M للكفاءة على CPU
        q4_idx = QUALITY_ORDER.index("Q4_K_M")
        quant_order = QUALITY_ORDER[q4_idx:] + QUALITY_ORDER[:q4_idx]

    ctx = context_length
    while ctx >= 512:
        for model in candidates:
            model_type = model.get("type")

            if model_type == "onnx":
                # نماذج ONNX ليس لها تكميم — نتحقّق فقط من min_ram_gb
                needed = float(model.get("min_ram_gb", 0))
                if avail_mem >= needed:
                    score = fit_score(hardware_profile, model, quant=None)
                    return {
                        "model": model["name"],
                        "quantization": None,
                        "estimated_vram_gb": needed,
                        "confidence": round(score / 100.0, 3),
                    }
                continue

            # نماذج LLM/embedding
            quantizations: list[str] = model.get("quantizations", [])
            # نرتّب التكميمات المتاحة وفق quant_order
            ordered_quants = [q for q in quant_order if q in quantizations]

            for quant in ordered_quants:
                needed = estimate_vram_gb(model["params_b"], quant, ctx)
                if needed <= avail_mem:
                    score = fit_score(hardware_profile, model, quant=quant)
                    return {
                        "model": model["name"],
                        "quantization": quant,
                        "estimated_vram_gb": round(needed, 3),
                        "confidence": round(score / 100.0, 3),
                    }

        # تقليص السياق ومحاولة مجدّداً
        ctx = ctx // 2

    return None


# ──────────────────────────────────────────────────────────────────────────────
# درجة التوافق
# ──────────────────────────────────────────────────────────────────────────────


def fit_score(
    hardware_profile: dict,
    model_config: dict,
    quant: str | None = None,
) -> float:
    """حساب درجة توافق النموذج مع العتاد (0-100).

    الأوزان:
    - 40%: هامش ذاكرة الرسوميّات/الذاكرة الرئيسيّة.
    - 30%: هامش الذاكرة الرئيسيّة الكليّة.
    - 20%: عدد أنوية المعالج.
    - 10%: جودة التكميم.

    Args:
        hardware_profile: ملف العتاد.
        model_config: إدخال النموذج من الكتالوج.
        quant: رمز التكميم المختار (``None`` لنماذج ONNX).

    Returns:
        درجة بين 0 و100 (float).
    """
    avail_mem = _available_memory_gb(hardware_profile)
    total_ram_gb = float(hardware_profile.get("total_ram_gb", 1.0))
    cpu_cores = int(hardware_profile.get("cpu_cores", 1))
    min_ram_gb = float(model_config.get("min_ram_gb", 1.0))
    params_b = float(model_config.get("params_b", 1.0))

    # ── حساب الذاكرة المطلوبة ────────────────────────────────────────────────
    if quant is not None and quant in QUANT_BPP:
        needed_mem = estimate_vram_gb(params_b, quant)
    else:
        # ONNX أو غير محدَّد — نستخدم min_ram_gb كتقدير
        needed_mem = min_ram_gb

    # ── مكوّن 1: هامش ذاكرة VRAM/RAM (40%) ──────────────────────────────────
    if needed_mem <= 0:
        mem_score: float = 100.0
    elif avail_mem <= 0:
        mem_score = 0.0
    else:
        headroom = (avail_mem - needed_mem) / avail_mem
        mem_score = max(0.0, min(100.0, headroom * 100.0))

    # ── مكوّن 2: هامش الذاكرة الرئيسيّة (30%) ───────────────────────────────
    if total_ram_gb <= 0:
        ram_score: float = 0.0
    else:
        ram_headroom = (total_ram_gb - min_ram_gb) / total_ram_gb
        ram_score = max(0.0, min(100.0, ram_headroom * 100.0))

    # ── مكوّن 3: أنوية المعالج (20%) ─────────────────────────────────────────
    # 8 أنوية = 100%، كل نواة إضافية تُضيف 5 نقاط (بحد أقصى 100)
    core_score = min(100.0, (cpu_cores / 8.0) * 100.0)

    # ── مكوّن 4: جودة التكميم (10%) ─────────────────────────────────────────
    if quant is None:
        quant_score: float = 80.0  # ONNX محسَّن عادةً
    elif quant == "F16":
        quant_score = 100.0
    elif quant in QUALITY_ORDER:
        idx = QUALITY_ORDER.index(quant)
        quant_score = 100.0 - idx * (100.0 / len(QUALITY_ORDER))
    else:
        quant_score = 50.0

    score = mem_score * 0.40 + ram_score * 0.30 + core_score * 0.20 + quant_score * 0.10
    return round(max(0.0, min(100.0, score)), 2)


# ──────────────────────────────────────────────────────────────────────────────
# دالّة مساعدة: عرض الكتالوج (للتشخيص)
# ──────────────────────────────────────────────────────────────────────────────


def catalog_summary(path: str | None = None) -> list[str]:
    """إرجاع قائمة بأسماء النماذج في الكتالوج (للتشخيص).

    Args:
        path: مسار ملف YAML (اختياري).

    Returns:
        قائمة بأسماء النماذج.
    """
    return [m.get("name", "?") for m in load_catalog(path)]


__all__ = [
    "QUANT_BPP",
    "QUALITY_ORDER",
    "catalog_summary",
    "estimate_vram_gb",
    "fit_score",
    "load_catalog",
    "recommend_model",
]
