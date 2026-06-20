"""api/calibration_ingest.py — مسار التحقّق/الإدخال لقيم المعايرة الإقليميّة (#382).

عند توفّر قياسات ميدانيّة حقيقيّة لمنطقة يمنيّة، تمرّ هنا أوّلاً: نتحقّق من كلّ حقل
يقدّمه المستخدِم ضدّ حدود زراعيّة آمنة، نقبل ما هو ضمن المدى ونرفض ما خرج عنه بسبب
عربيّ صريح. لا نُلفّق أيّ قيمة ولا نَكتب إلى `_REGION_OVERRIDES` وقت التشغيل — نُرجِع
كتلة تجاوز نظيفة مُتحقَّقة (`override_block`) لينسخها فريق التشغيل بعد المراجعة.

نقيّ حتميّ (لا I/O).
"""

from __future__ import annotations

# نطبّع المنطقة عبر الطبقة الأمّ (نفس مفاتيح/مرادفات `api.calibration`).
from api.calibration import normalize_region

# الحقل → (الحدّ الأدنى، الحدّ الأعلى، هل الأدنى مفتوح، هل الأعلى مفتوح).
# مفتوح = استبعاد الحدّ (strict)؛ مغلق = شموله.
_BOUNDS: dict[str, tuple[float, float, bool, bool]] = {
    "raw_fraction": (0.30, 0.70, False, False),
    "root_depth_m": (0.0, 3.0, True, False),  # (0, 3.0]
    "kc_dyn_min": (0.10, 0.50, False, False),
    "kc_dyn_max": (0.80, 1.50, False, False),
    "forecast_infiltration": (0.0, 1.0, False, False),
    "yield_uncertainty": (0.0, 1.0, False, False),
    "price_uncertainty": (0.0, 1.0, False, False),
}

_UPTAKE_KEYS = {"initial", "development", "mid", "late"}


def _check_bounds(field: str, value: float) -> str | None:
    """يُرجع سبب رفض عربيّاً إن خرجت القيمة عن المدى، وإلّا None."""
    lo, hi, lo_open, hi_open = _BOUNDS[field]
    lo_bad = value <= lo if lo_open else value < lo
    hi_bad = value >= hi if hi_open else value > hi
    if lo_bad or hi_bad:
        lo_br = "(" if lo_open else "["
        hi_br = ")" if hi_open else "]"
        return f"القيمة خارج المدى المسموح {lo_br}{lo}، {hi}{hi_br}"
    return None


def _validate_uptake(value: object) -> tuple[dict[str, float] | None, str | None]:
    """يتحقّق من نِسَب الامتصاص ككتلة واحدة. يُرجع (مقبول، سبب الرفض)."""
    if not isinstance(value, dict):
        return None, "يجب أن تكون نِسَب الامتصاص قاموساً"
    if set(value.keys()) != _UPTAKE_KEYS:
        return None, "مفاتيح نِسَب الامتصاص يجب أن تكون بالضبط {initial, development, mid, late}"
    for k, v in value.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None, f"قيمة نِسبة الامتصاص لـ{k} يجب أن تكون رقماً"
        if v < 0.0 or v > 1.0:
            return None, f"نِسبة الامتصاص لـ{k} خارج المدى [0، 1]"
    total = sum(float(v) for v in value.values())
    if abs(total - 1.0) > 0.01:
        return None, f"مجموع نِسَب الامتصاص يجب أن يساوي 1.0 ± 0.01 (الحاليّ {total})"
    return {k: float(v) for k, v in value.items()}, None


def validate_region_calibration(region: str, values: dict, source_ar: str | None = None) -> dict:
    """يتحقّق من قيم معايرة منطقة مقترَحة ضدّ حدود زراعيّة آمنة — نقيّ حتميّ.

    يفحص فقط الحقول التي يقدّمها المستدعي (كلّها اختياريّة). صدق: لا يُلفّق قيمة ولا
    يكتب إلى الحالة العامّة — يُرجِع `override_block` نظيفة لينسخها التشغيل يدويّاً.
    """
    key, _known = normalize_region(region)
    accepted: dict = {}
    rejected: list[dict] = []

    for field, value in values.items():
        if field == "uptake_fractions":
            ok, reason = _validate_uptake(value)
            if ok is not None:
                accepted[field] = ok
            else:
                rejected.append({"field": field, "value": value, "reason_ar": reason})
            continue
        if field not in _BOUNDS:
            rejected.append({"field": field, "value": value, "reason_ar": "حقل غير قابل للمعايرة"})
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            rejected.append(
                {"field": field, "value": value, "reason_ar": "القيمة يجب أن تكون رقماً"}
            )
            continue
        reason = _check_bounds(field, float(value))
        if reason is None:
            accepted[field] = float(value)
        else:
            rejected.append({"field": field, "value": value, "reason_ar": reason})

    # اتّساق Kc: إن قُبِل الحدّان معاً، يجب أن يكون الأدنى < الأعلى.
    if "kc_dyn_min" in accepted and "kc_dyn_max" in accepted:
        if not accepted["kc_dyn_min"] < accepted["kc_dyn_max"]:
            bad_min = accepted.pop("kc_dyn_min")
            bad_max = accepted.pop("kc_dyn_max")
            reason = "يجب أن يكون kc_dyn_min أصغر من kc_dyn_max"
            rejected.append({"field": "kc_dyn_min", "value": bad_min, "reason_ar": reason})
            rejected.append({"field": "kc_dyn_max", "value": bad_max, "reason_ar": reason})

    has_accepted = bool(accepted)
    validated = has_accepted and bool(source_ar)
    ready_to_persist = has_accepted and not rejected

    warnings_ar = [
        "لا يكتب القيم تلقائيّاً — انسخ override_block إلى _REGION_OVERRIDES بعد المراجعة",
    ]
    if not validated:
        if not has_accepted:
            warnings_ar.append("غير مُتحقَّق: لا حقول مقبولة (لا قيم ضمن المدى)")
        elif not source_ar:
            warnings_ar.append("غير مُتحقَّق: مصدر القياس (source_ar) مطلوب للتحقّق")
    if rejected and has_accepted:
        warnings_ar.append("بعض الحقول رُفِضت — راجِع rejected قبل الاعتماد")

    return {
        "region": key,
        "accepted": accepted,
        "rejected": rejected,
        "override_block": dict(accepted),
        "validated": validated,
        "source_ar": source_ar or None,
        "ready_to_persist": ready_to_persist,
        "calibrated": False,
        "warnings_ar": warnings_ar,
    }
