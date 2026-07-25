"""عقد الثقة المُركَّب (الشريحة 3، P0-4) — استبدال heuristic ``available_count`` العدديّ ببنية
ثقة مفسَّرة صادقة.

التدقيق (P0-4): ``confidence = "medium" if available_count >= 4 and degraded_count == 0 else "low"``
ثقةٌ عدديّة بسيطة — توفّر أربعة مكوّنات لا يعني أنّ التوصية موثوقة (قد تكون البيانات قديمة، أو
المحصول غير معروف، أو بلا معايرة محلّيّة). هذه الوحدة **تُضيف** (لا تكسر) بنية عوامل مُركَّبة تُظهر
**لماذا**، مع سقف صدق: لا تُمنَح درجة ``high`` ما دامت عوامل حرِجة (النضارة/المحاذاة/المعايرة/تحقّق
النموذج) **غير مُقيَّمة** — لأنّ المحرّك لا يملك مدخلاتها بعد. لا اختلاق: العامل غير القابل للحساب
يُوسَم ``not_assessed`` صراحةً، لا يُخمَّن.

نقيّة بالكامل. لا تغيّر سلسلة ``confidence`` القائمة (تبقى للتوافق) — تُقرَأ بجوارها.
"""

from __future__ import annotations

from typing import Any

# العوامل التي يحتاجها المحرّك بعدُ لكنّه لا يملك مدخلاتها (تُوسَم not_assessed بدل تخمين).
_UNASSESSED_FACTORS = (
    "freshness",  # يحتاج طوابع observed_at لكلّ منتج (P1-4)
    "spatial_alignment",  # يحتاج توافق المنطقة/الحقل (P1-15)
    "local_calibration",  # يحتاج معايرة محلّيّة (P0-5/P0-6)
    "model_validation",  # يحتاج تحقّق نموذج (P1-10/P1-12)
)

# حدّ اكتمال الأدلّة لبلوغ ``medium`` (نسبة المكوّنات المتوفّرة).
_MEDIUM_COMPLETENESS = 0.5


def compose_confidence(
    component_status: dict[str, str],
    *,
    crop_known: bool,
    recommendation_status: str | None = None,
) -> dict[str, Any]:
    """يُركِّب ثقةً مفسَّرةً من حالة المكوّنات الفعليّة + معرفة المحصول.

    يعيد ``{grade, factors, limits, unreachable}`` حيث ``grade ∈ {low, medium}`` (``high`` غير
    قابلة للبلوغ حتّى تُقيَّم العوامل المؤجَّلة — سقف صدق مُعلَن في ``unreachable``).
    """
    total = len(component_status) or 1
    available = sum(v == "available" for v in component_status.values())
    degraded = sum(v == "degraded" for v in component_status.values())
    completeness = round(available / total, 3)

    limits: list[str] = []
    if not crop_known:
        limits.append("crop_unknown")
    if degraded:
        limits.append("components_degraded")
    if recommendation_status and recommendation_status != "available":
        limits.append(f"recommendation_{recommendation_status}")
    limits.append("critical_factors_not_assessed")  # النضارة/المعايرة بعدُ غير مُقيَّمة

    # منطق الدرجة (أصرم من available_count وحده):
    #   * محصول غير معروف ⇒ low (لا ثقة توصية بلا هويّة محصول).
    #   * أيّ مكوّن مُدهوَر ⇒ low (جودة مشكوكة).
    #   * وإلّا: اكتمال ≥ العتبة ⇒ medium، دون ذلك ⇒ low.
    if not crop_known or degraded > 0:
        grade = "low"
    elif completeness >= _MEDIUM_COMPLETENESS:
        grade = "medium"
    else:
        grade = "low"

    factors: dict[str, Any] = {
        "evidence_completeness": {
            "score": completeness,
            "available": available,
            "total": total,
        },
        "degradation": {"degraded_count": degraded, "penalized": degraded > 0},
        "crop_identity": "known" if crop_known else "unknown",
    }
    for f in _UNASSESSED_FACTORS:
        factors[f] = "not_assessed"

    return {
        "grade": grade,
        "factors": factors,
        "limits": limits,
        # سقف صدق صريح: high غير قابلة للبلوغ قبل تقييم هذه العوامل (لا ادّعاء ثقة عالية).
        "unreachable": {"high": list(_UNASSESSED_FACTORS)},
    }
