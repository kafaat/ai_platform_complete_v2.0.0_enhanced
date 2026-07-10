"""gdd_shadow.py — مقارنة ظلّيّة لكلّ مستهلك GDD (WS-C.1c) — النواة الكنسيّة ↔ الإرث.

قرار المستخدم: **لا shadow موحَّد عامّ**. لكلّ مستهلك مقاييس منفصلة تُظهِر اختلاف
الطريقة صراحةً (لا تُذيبه في تسامح واسع). الإرث لا يدخل القرار قطّ — للمقارنة فقط.

المقاييس (لكلّ مستهلك):
  • ``absolute_daily_diff_max`` — أقصى فرق يوميّ مطلق (kernel).
  • ``accumulated_diff`` — فرق التراكميّ.
  • ``method_mismatch`` — طريقتا الحساب مختلفتان (simple ↔ modified) — **اختلاف دلاليّ**.
  • ``policy_mismatch`` — العتبات (base/cutoff) مختلفة بين الجانبين.
  • ``missing_day_count`` — أيّام تجاوزها المحرّك (غير محدودة/مفقودة).

``shadow_status`` (أولويّة تنازليّة): method_mismatch ⟶ policy_mismatch ⟶ value_diff ⟶ match.
اختلاف الطريقة **لا يُخفى بالتسامح**: يظهر كـ``method_mismatch`` مهما تطابقت القيمة.
"""

from __future__ import annotations

# المحرّك يُصرّح بدقّة 3 منازل؛ نقارن عندها (لا تسامح واسع). ضوضاء التقريب دون هذا
# لا تُعدّ اختلافاً قيميّاً — واختلاف الطريقة/السياسة يبقى مُصنَّفاً مستقلّاً مهما تطابقت القيمة.
_ENGINE_PRECISION = 3
_VALUE_MATCH_EPS = 1e-9


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compare_gdd_shadow(
    *,
    legacy_daily: list | None,
    legacy_accumulated: float | None,
    legacy_method: str,
    legacy_base_c: float | None,
    legacy_upper_cutoff_c: float | None,
    engine_product: dict,
) -> dict:
    """يقارن ناتج الإرث المحلّيّ بمنتج المحرّك الكنسيّ — لا يعدّل القرار.

    ``engine_product`` هو مخرَج ``/v1/weather/agro/gdd`` (daily_gdd/accumulated_gdd/
    thresholds_used). يعيد المقاييس الخمسة + ``shadow_status`` (مصنّف لا مُذاب).
    """
    thresholds = engine_product.get("thresholds_used", {}) or {}
    engine_method = thresholds.get("method")
    engine_daily = engine_product.get("daily_gdd") or []
    engine_accumulated = _num(engine_product.get("accumulated_gdd"))
    legacy_acc = _num(legacy_accumulated)

    # اختلاف الطريقة — دلاليّ، يُظهَر صراحةً (لا يُذاب بالتسامح).
    method_mismatch = bool(legacy_method) and legacy_method != engine_method

    # اختلاف السياسة — العتبات المُستخدَمة على الجانبين.
    policy_mismatch = (_num(legacy_base_c) != _num(thresholds.get("base_c"))) or (
        _num(legacy_upper_cutoff_c) != _num(thresholds.get("upper_cutoff_c"))
    )

    # أقصى فرق يوميّ مطلق عند دقّة المحرّك (متجاهلاً None في أيّ جانب).
    daily_diff_max = None
    ld = legacy_daily or []
    for i in range(min(len(ld), len(engine_daily))):
        lv, ev = _num(ld[i]), _num(engine_daily[i])
        if lv is None or ev is None:
            continue
        d = abs(round(lv, _ENGINE_PRECISION) - round(ev, _ENGINE_PRECISION))
        daily_diff_max = d if daily_diff_max is None else max(daily_diff_max, d)

    accumulated_diff = (
        round(engine_accumulated - round(legacy_acc, _ENGINE_PRECISION), _ENGINE_PRECISION)
        if (engine_accumulated is not None and legacy_acc is not None)
        else None
    )
    missing_day_count = sum(1 for v in engine_daily if v is None)

    if method_mismatch:
        status = "method_mismatch"
    elif policy_mismatch:
        status = "policy_mismatch"
    elif accumulated_diff is not None and abs(accumulated_diff) > _VALUE_MATCH_EPS:
        status = "value_diff"
    elif accumulated_diff is None:
        status = "incomparable"
    else:
        status = "match"

    return {
        "absolute_daily_diff_max": (
            round(daily_diff_max, 6) if daily_diff_max is not None else None
        ),
        "accumulated_diff": accumulated_diff,
        "method_mismatch": method_mismatch,
        "policy_mismatch": policy_mismatch,
        "missing_day_count": missing_day_count,
        "shadow_status": status,
        "legacy_method": legacy_method,
        "engine_method": engine_method,
    }
