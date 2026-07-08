"""core/spray_readiness.py — قرار «هل أرشّ الآن؟» (go/no-go) — منطق صرف يوحّد عاملَين قائمَين.

سؤال المزارع الحقيقيّ ليس «كم سرعة الريح» بل **«هل أرشّ الآن؟»**. هذا المُوحِّد يجمع:
  • صلاحيّة الطقس للرشّ (``_operation_suitability(spraying)`` — ريح/هبّات/حرارة/رطوبة/مطر).
  • خطر انجراف الرشّ نحو الجوار (``spray_drift_risk`` — downwind نحو مناطق حسّاسة).
ويُخرِج قراراً واحداً بأسوأ العاملَين (الأكثر تقييداً يحكم). **لا يُعيد حساب أيّهما** — يدمج
مخرَجيهما فقط (مصدر واحد لكلّ منطق).

**صدق:** كلا المدخلَين مجهول/ناقص ⇒ ``unknown`` (لا قرار بلا أساس). خطر الانجراف الفعليّ
حاجب مطلق (no_go) — سلامة الجوار تسبق راحة التوقيت. القرار النهائيّ ميدانيّ.
"""

from __future__ import annotations

from typing import Any

# ترتيب الشدّة (الأعلى يحكم عند الدمج).
_SEVERITY = {"go": 0, "caution": 1, "no_go": 2}
_LABEL = {0: "go", 1: "caution", 2: "no_go"}

# صلاحيّة الطقس (تسمية _operation_suitability) → قرار جزئيّ.
_WEATHER_DECISION = {
    "optimal": "go",
    "acceptable": "go",
    "poor": "caution",
    "unsafe": "no_go",
}


def spray_go_no_go(wind_suitability: Any = None, drift_risk: Any = None) -> dict[str, Any]:
    """قرار الرشّ النهائيّ من صلاحيّة الطقس + خطر الانجراف. أسوأ العاملَين يحكم.

    ``wind_suitability``: مخرَج ``_operation_suitability`` (``{suitability, score,
    limiting_factors}``) أو None. ``drift_risk``: مخرَج ``spray_drift_risk``
    (``{status: at_risk/clear/unknown, exposed_zones}``) أو None. مجهولان ⇒ unknown.
    """
    reasons: list[str] = []
    severities: list[int] = []

    # عامل الطقس.
    weather_label = None
    if isinstance(wind_suitability, dict):
        weather_label = str(wind_suitability.get("suitability") or "").lower() or None
        dec = _WEATHER_DECISION.get(weather_label)
        if dec is not None:
            severities.append(_SEVERITY[dec])
            if dec != "go":
                factors = wind_suitability.get("limiting_factors") or []
                reasons.append(
                    f"طقس {weather_label}"
                    + (f" ({', '.join(str(f) for f in factors)})" if factors else "")
                )

    # عامل الانجراف — الخطر الفعليّ حاجب مطلق (سلامة الجوار).
    drift_status = None
    if isinstance(drift_risk, dict):
        drift_status = str(drift_risk.get("status") or "").lower() or None
        if drift_status == "at_risk":
            severities.append(_SEVERITY["no_go"])
            n = len(drift_risk.get("exposed_zones") or [])
            reasons.append(f"انجراف نحو {n} منطقة حسّاسة downwind")
        elif drift_status == "clear":
            severities.append(_SEVERITY["go"])
        # unknown ⇒ لا يرفع الشدّة (لا نحجب بلا دليل انجراف).

    if not severities:
        return {
            "decision": "unknown",
            "reason": "no_inputs",
            "weather_suitability": weather_label,
            "drift_status": drift_status,
            "reasons": [],
        }

    decision = _LABEL[max(severities)]
    if decision == "go" and not reasons:
        reasons.append("الطقس مناسب ولا انجراف نحو الجوار")
    return {
        "decision": decision,
        "reason": None,
        "weather_suitability": weather_label,
        "drift_status": drift_status,
        "reasons": reasons,
        "note_ar": "قرار مساعد يوحّد الطقس والانجراف — القرار النهائيّ ميدانيّ.",
    }
