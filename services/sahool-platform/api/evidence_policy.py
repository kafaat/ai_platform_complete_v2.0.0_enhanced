"""سياسة دليل القرار (C5) — يوسم دور NDVI في القرار بصدق ومعايرة.

أفضل ممارسة: يبقى NDVI **إشارةً مساعدة** لا «حاكماً قانونيّاً» إلّا بعد **معايرة
ميدانيّة**. لا عتبة NDVI عالميّة ثابتة («<0.4 = خطر») تصلح لكلّ محصول/منطقة. هذه
السياسة تصنّف دور NDVI في قرارٍ ما إلى:

  • ``informational``     — لا قيمة محسوبة (أو غير ذي صلة) ⇒ يُعرَض فقط.
  • ``supporting``        — **الافتراضيّ**: قيمة موجودة، تدعم لكن **لا تحجب** قراراً.
  • ``decision_blocking`` — يحجب/يصعّد قراراً، **فقط** عند اجتماع كلّ الشروط:
        محصول معروف + طور نموّ + تاريخ زراعة + **معايرة محليّة** + جودة مشهد
        (غيوم/نضارة مقبولة). دون أيٍّ منها ⇒ ``supporting`` (لا حجب).

**صدق:** هذه السياسة تمنع NDVI من قلب قرارٍ قانونيّ/تشغيليّ وحده دون معايرة. ربط
عتبات NDVI بقرار فعليّ يتطلّب **تحقّقاً ميدانيّاً** لمحاصيل/أطوار اليمن — تبقى
``fixed`` لا ``verified``.
"""

from __future__ import annotations

# أدوار الدليل (مجموعة مغلقة).
EVIDENCE_INFORMATIONAL = "informational"
EVIDENCE_SUPPORTING = "supporting"
EVIDENCE_DECISION_BLOCKING = "decision_blocking"

# عتبات جودة المشهد الافتراضيّة لاعتماد NDVI حاجباً (قابلة للضبط عند الاستدعاء).
DEFAULT_MAX_CLOUD_PCT = 20.0
DEFAULT_MAX_NDVI_AGE_DAYS = 14.0


def classify_ndvi_evidence(
    *,
    ndvi_mean: float | None,
    ndvi_age_days: float | None = None,
    crop: str | None = None,
    growth_stage: str | None = None,
    planting_date=None,
    locally_calibrated: bool = False,
    cloud_pct: float | None = None,
    scl_valid: bool | None = None,
    max_cloud_pct: float = DEFAULT_MAX_CLOUD_PCT,
    max_age_days: float = DEFAULT_MAX_NDVI_AGE_DAYS,
) -> dict:
    """يصنّف دور NDVI في قرار. يُرجِع dict:
    ``role`` · ``confidence`` (0..1) · ``calibrated`` · ``reason_ar`` · ``ndvi_mean``.

    **ثابت السلامة:** لا يُرجِع ``decision_blocking`` أبداً ما لم تكن
    ``locally_calibrated=True`` **و** سياق المحصول كامل **و** جودة المشهد مقبولة.
    """
    if ndvi_mean is None:
        return {
            "role": EVIDENCE_INFORMATIONAL,
            "confidence": 0.0,
            "calibrated": False,
            "reason_ar": "لا قيمة NDVI محسوبة — معلوماتيّ فقط (لا تلفيق).",
            "ndvi_mean": None,
        }

    # جودة المشهد: غيوم تحت العتبة + ليس بايتاً + SCL غير مرفوض.
    quality_ok = (
        (cloud_pct is None or float(cloud_pct) <= max_cloud_pct)
        and (ndvi_age_days is None or float(ndvi_age_days) <= max_age_days)
        and (scl_valid is not False)
    )
    # سياق زراعيّ كامل (لا عتبة عالميّة — العتبة تعتمد المحصول/الطور).
    context_ok = bool(crop) and bool(growth_stage) and bool(planting_date)

    if locally_calibrated and context_ok and quality_ok:
        return {
            "role": EVIDENCE_DECISION_BLOCKING,
            "confidence": 0.85,
            "calibrated": True,
            "reason_ar": (
                "NDVI معايَر محليّاً + سياق محصول كامل + جودة مشهد مقبولة ⇒ "
                "يحجب/يصعّد القرار (عتبة خاصّة بالمحصول/الطور لا عالميّة)."
            ),
            "ndvi_mean": float(ndvi_mean),
        }

    # الافتراضيّ: داعم لا حاجب — يُبيّن السبب الناقص بصدق.
    missing: list[str] = []
    if not locally_calibrated:
        missing.append("معايرة محليّة")
    if not context_ok:
        missing.append("سياق محصول كامل (محصول/طور/تاريخ زراعة)")
    if not quality_ok:
        missing.append("جودة مشهد (غيوم/نضارة)")
    confidence = 0.5 if quality_ok else 0.3
    return {
        "role": EVIDENCE_SUPPORTING,
        "confidence": confidence,
        "calibrated": False,
        "reason_ar": (
            "NDVI داعم لا حاجب (لا يقلب القرار وحده). ناقص للاعتماد الحاجب: "
            + "، ".join(missing)
            + "."
        ),
        "ndvi_mean": float(ndvi_mean),
    }


def ndvi_evidence_entry(**kwargs) -> dict:
    """يبني مُدخَل ``evidence[]`` موحّداً لـNDVI (مصدر + دور + ثقة + سبب)."""
    cls = classify_ndvi_evidence(**kwargs)
    return {
        "source": "sentinel-2 (raster-service)",
        "kind": "ndvi",
        "role": cls["role"],
        "value": cls["ndvi_mean"],
        "confidence": cls["confidence"],
        "calibrated": cls["calibrated"],
        "note_ar": cls["reason_ar"],
    }
