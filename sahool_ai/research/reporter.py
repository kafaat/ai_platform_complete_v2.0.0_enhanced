"""توليد تقارير JSON وMarkdown وبيانات خرائط GeoJSON.

Report generator for the SAHOOL Agronomic Research Pipeline.
Produces structured JSON, Arabic Markdown, and valid GeoJSON map data.
"""

from __future__ import annotations

from sahool_ai.research.models import Synthesis

# ── تعيين مستوى التنبيه / Alert level mapping ──────────────────────────────
_SEVERITY_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}
_ALERT_LEVELS: dict[str, str] = {
    "high": "critical",
    "medium": "warning",
    "low": "info",
}

# ── إحداثيّات مرجعيّة للمناطق / Region centroids (Yemen, approximate) ─────
_REGION_CENTROIDS: dict[str, list[float]] = {
    "north_sector": [44.20, 15.55],
    "south_sector": [44.20, 12.80],
    "east_sector": [47.00, 15.20],
    "west_sector": [42.80, 15.20],
}
_DEFAULT_CENTROID: list[float] = [44.20, 15.35]  # صنعاء تقريباً


def generate_json_report(synthesis: Synthesis) -> dict:
    """توليد تقرير JSON منظَّم من نتيجة التوليف.

    Args:
        synthesis: نتيجة التوليف من ``synthesize_findings``.

    Returns:
        قاموس يحتوي على: summary, factors, recommendations, confidence,
        alert_level, factor_count.
    """
    # Determine overall alert level from highest-severity factor
    max_severity = "low"
    for factor in synthesis.factors:
        if _SEVERITY_ORDER.get(factor.severity, 0) > _SEVERITY_ORDER.get(max_severity, 0):
            max_severity = factor.severity

    return {
        "summary": synthesis.summary,
        "factors": [
            {
                "name": f.name,
                "description": f.description,
                "severity": f.severity,
                "confidence": round(f.confidence, 4),
            }
            for f in synthesis.factors
        ],
        "recommendations": synthesis.recommendations,
        "confidence": round(synthesis.confidence, 4),
        "alert_level": _ALERT_LEVELS.get(max_severity, "info"),
        "factor_count": len(synthesis.factors),
    }


def generate_markdown_report(synthesis: Synthesis) -> str:
    """توليد تقرير Markdown عربي من نتيجة التوليف.

    يشمل الأقسام: الملخّص / العوامل / التوصيات / مستوى الثقة.

    Args:
        synthesis: نتيجة التوليف من ``synthesize_findings``.

    Returns:
        نصّ Markdown UTF-8 بأقسام عربيّة.
    """
    lines: list[str] = []

    # ── الملخّص ────────────────────────────────────────────────────────────
    lines.append("## الملخّص")
    lines.append("")
    lines.append(synthesis.summary)
    lines.append("")

    # ── العوامل ────────────────────────────────────────────────────────────
    lines.append("## العوامل")
    lines.append("")
    if synthesis.factors:
        for factor in synthesis.factors:
            severity_ar = {"low": "منخفض", "medium": "متوسّط", "high": "مرتفع"}.get(
                factor.severity, factor.severity
            )
            lines.append(f"### {factor.name}")
            lines.append("")
            lines.append(f"- **الشدّة:** {severity_ar}")
            lines.append(f"- **الثقة:** {factor.confidence:.0%}")
            lines.append(f"- **الوصف:** {factor.description}")
            lines.append("")
    else:
        lines.append("_لم تُرصد عوامل بارزة._")
        lines.append("")

    # ── التوصيات ───────────────────────────────────────────────────────────
    lines.append("## التوصيات")
    lines.append("")
    if synthesis.recommendations:
        for i, rec in enumerate(synthesis.recommendations, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")
    else:
        lines.append("_لا توصيات محدَّدة في الوقت الحالي._")
        lines.append("")

    # ── مستوى الثقة ────────────────────────────────────────────────────────
    lines.append("## مستوى الثقة")
    lines.append("")
    lines.append(f"**الثقة الإجمالية:** {synthesis.confidence:.0%}")
    lines.append("")

    return "\n".join(lines)


def generate_map_data(synthesis: Synthesis, region: str | None = None) -> dict:
    """توليد بيانات خريطة GeoJSON صالحة من نتيجة التوليف.

    Args:
        synthesis: نتيجة التوليف من ``synthesize_findings``.
        region: رمز المنطقة (اختياري) لتحديد موقع الميزة الجغرافيّة.

    Returns:
        GeoJSON FeatureCollection صالح يحتوي على ميزة واحدة على الأقل.
    """
    # Determine alert level
    max_severity = "low"
    for factor in synthesis.factors:
        if _SEVERITY_ORDER.get(factor.severity, 0) > _SEVERITY_ORDER.get(max_severity, 0):
            max_severity = factor.severity

    alert_level = _ALERT_LEVELS.get(max_severity, "info")

    # Resolve centroid
    centroid = _REGION_CENTROIDS.get(region or "", _DEFAULT_CENTROID)

    # Build feature properties (Arabic labels for user-facing fields)
    properties: dict = {
        "region": region or "غير محدَّد",
        "alert_level": alert_level,
        "confidence": round(synthesis.confidence, 4),
        "factor_count": len(synthesis.factors),
        "factors": [f.name for f in synthesis.factors],
        "summary_ar": synthesis.summary[:200],  # truncate for map tooltip
    }

    feature: dict = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": centroid,
        },
        "properties": properties,
    }

    return {
        "type": "FeatureCollection",
        "features": [feature],
    }
