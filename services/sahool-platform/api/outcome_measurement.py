"""api/outcome_measurement.py — قياس نتائج القرار (Outcome Measurement)

#383: الطبقة التي تفرّق بين «نظام دعم قرار» و«نظام تشغيل». حتى الآن السلسلة:
رصد → تنبّؤ → قرار. هذه تضيف الخطوة التالية: **قياس النتيجة الفعليّة** للقرار:

  هل اتُّبِع الريّ الموصى به؟ هل تحقّق الوفر المائيّ؟ هل وقع الإجهاد كما تُنبِّئ؟
  هل بلغ الإنتاج الهدف؟

نقيّة حتميّة (لا I/O). تقارن **المُخطَّط** (من القرار/الخطّة) بـ**المرصود** (قياس
ميدانيّ). صدق: تُقيِّم فقط ما توفّر طرفاه (مُخطَّط ومرصود)؛ الناقص يُعلَن «يحتاج بيانات»
لا يُفبرَك. هذه نصف حلقة التعلّم؛ «التعلّم» (تعديل المعايرة) طبقة لاحقة مستقلّة.
"""

from __future__ import annotations

# هامش تطابق الريّ (±) لاعتبار القرار «مُتَّبَعاً» — نسبة من المُخطَّط. تقديريّ.
_IRRIGATION_TOLERANCE = 0.15
# عتبة بلوغ الإنتاج المستهدف (نسبة من المتوقّع). تقديريّ.
_YIELD_MET_FRACTION = 0.90


def _delta(actual: float | None, planned: float | None) -> float | None:
    if actual is None or planned is None:
        return None
    return round(actual - planned, 2)


def measure_outcome(planned: dict, actual: dict) -> dict:
    """يقارن قرار/خطّة بالنتيجة الفعليّة المرصودة ⇒ تقييم لكلّ مقياس — نقيّ حتميّ.

    planned: {recommended_irrigation_mm, predicted_stress_days, expected_yield_t_ha,
              season_budget_mm}. actual: {actual_irrigation_mm, observed_stress_days,
              actual_yield_t_ha, actual_water_used_mm}. كلّها اختياريّة.
    صدق: مقياس بلا طرفَيه ⇒ status=needs_data (لا حكم مُختلق).
    """
    metrics: list[dict] = []
    success_flags: list[str] = []
    warnings_ar: list[str] = []

    # ١) اتّباع الريّ: المرصود مقابل الموصى به.
    rec = planned.get("recommended_irrigation_mm")
    act_irr = actual.get("actual_irrigation_mm")
    if rec is not None and act_irr is not None:
        d = act_irr - rec
        tol = abs(rec) * _IRRIGATION_TOLERANCE
        if abs(d) <= tol:
            status, label = "followed", "اتُّبِع الريّ الموصى به"
            success_flags.append("irrigation_followed")
        elif d < 0:
            status, label = "under", "ريّ أقلّ من الموصى به (احتمال إجهاد)"
        else:
            status, label = "over", "ريّ أكثر من الموصى به (هدر محتمل)"
        metrics.append(
            {
                "key": "irrigation",
                "planned": rec,
                "actual": act_irr,
                "delta": round(d, 2),
                "status": status,
                "label_ar": label,
            }
        )
    else:
        metrics.append(
            {
                "key": "irrigation",
                "status": "needs_data",
                "label_ar": "يحتاج الريّ الموصى به والمرصود",
            }
        )

    # ٢) الإجهاد: المرصود مقابل المُتنبَّأ (أقلّ = أفضل).
    pred_s = planned.get("predicted_stress_days")
    obs_s = actual.get("observed_stress_days")
    if pred_s is not None and obs_s is not None:
        if obs_s < pred_s:
            status, label = "better", "إجهاد أقلّ من المتوقّع"
            success_flags.append("stress_better")
        elif obs_s == pred_s:
            status, label = "as_predicted", "الإجهاد كما تُنبِّئ"
        else:
            status, label = "worse", "إجهاد أكثر من المتوقّع — راجِع الخطّة"
        if obs_s == 0:
            success_flags.append("stress_avoided")
        metrics.append(
            {
                "key": "stress",
                "predicted": pred_s,
                "observed": obs_s,
                "delta": obs_s - pred_s,
                "status": status,
                "label_ar": label,
            }
        )
    else:
        metrics.append(
            {"key": "stress", "status": "needs_data", "label_ar": "يحتاج الإجهاد المتنبَّأ والمرصود"}
        )

    # ٣) الإنتاج: الفعليّ مقابل المتوقّع.
    exp_y = planned.get("expected_yield_t_ha")
    act_y = actual.get("actual_yield_t_ha")
    if exp_y is not None and act_y is not None and exp_y > 0:
        ratio = act_y / exp_y
        if ratio >= 1.0:
            status, label = "above", "تجاوز الإنتاج المتوقّع"
            success_flags.append("yield_met")
        elif ratio >= _YIELD_MET_FRACTION:
            status, label = "met", "بلغ الإنتاج المستهدف تقريباً"
            success_flags.append("yield_met")
        else:
            status, label = "below", "إنتاج دون المتوقّع"
        metrics.append(
            {
                "key": "yield",
                "expected": exp_y,
                "actual": act_y,
                "delta": _delta(act_y, exp_y),
                "ratio": round(ratio, 3),
                "status": status,
                "label_ar": label,
            }
        )
    else:
        metrics.append(
            {"key": "yield", "status": "needs_data", "label_ar": "يحتاج الإنتاج المتوقّع والفعليّ"}
        )

    # ٤) الوفر/الميزانيّة المائيّة: الماء الفعليّ مقابل الميزانيّة.
    budget = planned.get("season_budget_mm")
    used = actual.get("actual_water_used_mm")
    if budget is not None and used is not None:
        d = used - budget
        if used <= budget:
            status, label = "within", "ضمن الميزانيّة المائيّة"
            success_flags.append("water_within_budget")
        else:
            status, label = "exceeded", "تجاوز الميزانيّة المائيّة"
        metrics.append(
            {
                "key": "water_budget",
                "planned": budget,
                "actual": used,
                "delta": round(d, 2),
                "status": status,
                "label_ar": label,
            }
        )
    else:
        metrics.append(
            {
                "key": "water_budget",
                "status": "needs_data",
                "label_ar": "يحتاج الميزانيّة والماء المستهلَك",
            }
        )

    evaluated = [m for m in metrics if m["status"] != "needs_data"]
    data_completeness = round(len(evaluated) / len(metrics), 2) if metrics else 0.0
    if not evaluated:
        warnings_ar.append("لا مقياس قابل للتقييم — زوّدنا بقياسات ميدانيّة (ريّ/إجهاد/إنتاج)")

    return {
        "metrics": metrics,
        "success_flags": success_flags,
        "n_evaluated": len(evaluated),
        "n_success": len(success_flags),
        "data_completeness": data_completeness,
        "calibrated": False,
        "warnings_ar": warnings_ar,
    }
