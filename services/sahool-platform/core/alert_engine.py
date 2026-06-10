"""
alert_engine.py — محرّك التنبيهات الاستباقي (proactive alerting).

الفجوة المُسدَّة: النظام يحسب operational_truths غنيّة (salinity_class/risk،
crop_vigor، heat_risk، ndvi_trend) + كشف التغيير المكاني (degraded_pct) + FVC
(desertification_pct) — لكنّه كان **سلبيّاً**: ينتظر أن يسأل المزارع. لا محرّك
يراقب الحالة ويُطلق إنذاراً. حرجٌ للجوف: المزارع لا يفتح اللوحة يوميّاً، يحتاج
إنذاراً يصله عند الخطر.

هذا المحرّك نقيّ (لا I/O): يقرأ الحالة الموحّدة (+ نتائج change_detection/FVC
اختياريّاً) ويُنتج تنبيهات مُصنّفة. يفصل المنطق عن التوصيل: يُنتج التنبيه فقط؛
الإرسال الفعلي (تطبيق/WhatsApp/SMS) طبقة قناة لاحقة.

كبح الإنذار الكاذب (حماية ثقة المزارع):
  • لا تنبيه «حرج» على ثقة حالة منخفضة (يُخفَّض لتحذير مع وسم).
  • لا تنبيه تدهور/تصحّر على تغطية صالحة منخفضة (<50% — غيوم/فجوات).

العتبات من الأدبيّات العامّة — عايِرها بحقول الجوف.
"""

from __future__ import annotations

from typing import Any

CRITICAL = "critical"
WARNING = "warning"
INFO = "info"
_SEVERITY_RANK = {CRITICAL: 3, WARNING: 2, INFO: 1}

# عتبات (قابلة للمعايرة)
_SALINITY_RISK = 0.75
_VIGOR_LOW = 0.4
_HEAT_HIGH = 0.7
_DEGRADED_PCT = 25.0
_SEVERE_PCT = 10.0
_DESERT_PCT = 40.0
_MIN_COVERAGE = 50.0  # تغطية صالحة دونها تُكبَح تنبيهات التدهور/التصحّر


def evaluate_alerts(
    state: Any,
    change_result: dict | None = None,
    fvc_result: dict | None = None,
) -> list[dict]:
    """يقيّم الحالة الموحّدة (+ نتائج مكانيّة اختياريّة) ويُنتج تنبيهات مُصنّفة.

    state: كائن له operational_truths (dict) و confidence (str) و contradictions
           (list) — أي CanonicalFieldState.
    change_result: ناتج /change/detect (اختياري) — يُفعّل تنبيه التدهور المكاني.
    fvc_result: ناتج /fvc/compute (اختياري) — يُفعّل تنبيه التصحّر.
    """
    truths: dict = getattr(state, "operational_truths", {}) or {}
    confidence = getattr(state, "confidence", "medium")
    contradictions = getattr(state, "contradictions", []) or []
    low_conf = confidence in ("none", "low")

    alerts: list[dict] = []

    def add(severity: str, code: str, message_ar: str, **extra: Any) -> None:
        # كبح: لا «حرج» على ثقة منخفضة — يُخفَّض لتحذير موسوم (لا نُفزع ببيانات ضعيفة)
        if severity == CRITICAL and low_conf:
            severity = WARNING
            message_ar = "(ثقة منخفضة — تحقّق ميداني) " + message_ar
        alerts.append({"severity": severity, "code": code, "message_ar": message_ar, **extra})

    # ── ملوحة حرجة (حرج للجوف: CaCO3 + ريّ مالح) ──
    sal_class = truths.get("salinity_class")
    sal_risk = truths.get("salinity_risk")
    if sal_class == "critical" or (
        isinstance(sal_risk, int | float) and sal_risk >= _SALINITY_RISK
    ):
        add(
            CRITICAL,
            "salinity_critical",
            "ملوحة حرجة: غسيل + تحسين الصرف عاجلاً، وتجنّب الريّ المالح؛ راعِ الكلس (CaCO3).",
            value=sal_risk,
        )

    # ── ضعف الحيويّة ──
    vigor = truths.get("crop_vigor")
    if isinstance(vigor, int | float) and vigor < _VIGOR_LOW:
        add(
            WARNING, "low_vigor", f"حيويّة منخفضة ({vigor}): افحص الريّ/التغذية ميدانيّاً.", value=vigor
        )

    # ── إجهاد حراري ──
    heat = truths.get("heat_risk")
    if isinstance(heat, int | float) and heat >= _HEAT_HIGH:
        add(WARNING, "heat_stress", "إجهاد حراري مرتفع — قدّم/زِد الريّ وراقب الإجهاد.", value=heat)

    # ── تراجع NDVI (إنذار مبكر) ──
    if truths.get("ndvi_trend") == "decreasing":
        add(INFO, "ndvi_decline", "اتّجاه NDVI هابط — إنذار مبكر، تابع عن قرب حتّى لو القيمة طبيعيّة.")

    # ── تدهور مكاني (ربط change_detection) — مكبوح على تغطية منخفضة ──
    if change_result:
        cov = float(change_result.get("coverage_pct", 100.0))
        areas = change_result.get("areas", {}) or {}
        degraded = float(areas.get("degraded_pct", 0.0))
        severe = float(areas.get("severe_degraded_pct", 0.0))
        if cov >= _MIN_COVERAGE and degraded >= _DEGRADED_PCT:
            sev = CRITICAL if severe >= _SEVERE_PCT else WARNING
            add(
                sev,
                "spatial_degradation",
                f"تدهور مكاني: {degraded}% من الحقل ({severe}% بشدّة) — راجع خريطة الفرق.",
                degraded_pct=degraded,
                severe_pct=severe,
            )

    # ── تصحّر / تغطية منخفضة (ربط FVC) — مكبوح على تغطية منخفضة ──
    if fvc_result:
        cov = float(fvc_result.get("coverage_pct", 100.0))
        desert = float((fvc_result.get("areas", {}) or {}).get("desertification_pct", 0.0))
        if cov >= _MIN_COVERAGE and desert >= _DESERT_PCT:
            add(
                WARNING,
                "desertification",
                f"تغطية نباتيّة منخفضة على {desert}% من الحقل — تصحّر محتمل.",
                desertification_pct=desert,
            )

    # ── تناقضات الحالة (شفافيّة، لا قرار) ──
    for c in contradictions:
        add(INFO, "state_contradiction", f"تناقض في الحالة يحتاج انتباهاً: {c}")

    return alerts


def summarize_alerts(alerts: list[dict]) -> dict:
    """ملخّص: العدد لكلّ خطورة + الأعلى أولويّة + هل يوجد حرج."""
    by_severity = {CRITICAL: 0, WARNING: 0, INFO: 0}
    for a in alerts:
        by_severity[a.get("severity", INFO)] = by_severity.get(a.get("severity", INFO), 0) + 1
    top = max(alerts, key=lambda a: _SEVERITY_RANK.get(a.get("severity"), 0), default=None)
    return {
        "total": len(alerts),
        "by_severity": by_severity,
        "has_critical": by_severity[CRITICAL] > 0,
        "top_priority": top,
    }
