"""api/irrigation_state_guard.py — بوّابة اتّساق/نضارة حالة الريّ (WS-D.2) — نقيّة.

قبل إنتاج توصية ريّ مُثراة تلقائيّاً من حالة الحقل (دفتر المياه + بارامترات التربة)،
يجب التحقّق صراحةً — لا قصّ صامت، لا استبدال صفر للنقص:

  • الاكتمال: غياب Dr أو TAW ⇒ ``insufficient_data`` (مفقود ≠ صفر؛ لا تُختلَق قيمة).
  • الاتّساق: ``0 ≤ Dr ≤ TAW`` (الاستنزاف لا يتجاوز الماء المتاح الكلّيّ). تجاوز Dr
    لـTAW (اختلاف طوابع زمنيّة/خطأ تسوية) ⇒ ``inconsistent_state`` والتوصية
    **unavailable** — ولا يُقصّ Dr صامتاً إلى TAW.
  • النضارة: عمر دفتر المياه ≤ عتبة؛ أقدم ⇒ قيدٌ مُعلَن (``stale_water_ledger``) لا
    حجب (استنزاف قديم يبقى إشارة مع تحذير صريح).
  • مصدر TAW: يُعلَن (مختبر/نسيج/افتراضيّ محصول) — غير المُعايَر يُوسَم قيداً.

نقيّة حتميّة (لا I/O، لا وصول env) — كلّ المدخلات تُمرَّر صراحةً؛ تُختبَر بلا قاعدة.
"""

from __future__ import annotations

# نضارة دفتر المياه الافتراضيّة (ساعات) — استنزاف أقدم منها يقود قراراً حاضراً بحذر.
DEFAULT_MAX_LEDGER_AGE_HOURS = 72.0

# مصادر TAW التي تُعدّ غير مُعايَرة يمنيّاً (تُوسَم قيداً على الثقة، لا تحجب).
_UNCALIBRATED_TAW_SOURCES = frozenset({None, "texture_fallback", "crop_default", "model_estimate"})


def assess_irrigation_state(
    *,
    depletion_mm: float | None,
    taw_mm: float | None,
    ledger_age_hours: float | None = None,
    taw_source: str | None = None,
    max_ledger_age_hours: float = DEFAULT_MAX_LEDGER_AGE_HOURS,
) -> dict:
    """يُقيّم صلاحيّة حالة الماء لإنتاج توصية ريّ — نقيّ، fail-closed، لا قصّ.

    Returns dict:
        ``status`` (recommendation_ready | insufficient_data | inconsistent_state) ·
        ``available`` (bool: هل يجوز إنتاج توصية) · ``limitations`` (قائمة أسباب مُعلَنة) ·
        ``depletion_fraction`` (Dr/TAW أو None) · ``taw_source``.
    """
    # (1) الاكتمال — مفقود ليس صفراً.
    missing = []
    if depletion_mm is None:
        missing.append("missing_depletion_mm")
    if taw_mm is None:
        missing.append("missing_taw_mm")
    if missing:
        return {
            "status": "insufficient_data",
            "available": False,
            "limitations": missing,
            "depletion_fraction": None,
            "taw_source": taw_source,
        }

    dr = float(depletion_mm)
    taw = float(taw_mm)

    # (2) الاتّساق — 0 ≤ Dr ≤ TAW، بلا قصّ صامت.
    if taw <= 0 or dr < 0 or dr > taw:
        reason = "depletion_exceeds_taw" if (taw > 0 and dr > taw) else "invalid_depletion_or_taw"
        return {
            "status": "inconsistent_state",
            "available": False,
            "limitations": [reason],
            "depletion_fraction": (round(dr / taw, 3) if taw > 0 else None),
            "taw_source": taw_source,
        }

    # (3) قيود لا تحجب (نضارة + معايرة TAW).
    limitations: list[str] = []
    if ledger_age_hours is not None and ledger_age_hours > max_ledger_age_hours:
        limitations.append("stale_water_ledger")
    if taw_source in _UNCALIBRATED_TAW_SOURCES:
        limitations.append("taw_uncalibrated")

    return {
        "status": "recommendation_ready",
        "available": True,
        "limitations": limitations,
        "depletion_fraction": round(dr / taw, 3),
        "taw_source": taw_source,
    }
