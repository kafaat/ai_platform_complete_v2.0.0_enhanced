"""Reports for the deterministic agricultural research simulation."""

from __future__ import annotations

from sahool_ai.research.models import Synthesis


def generate_json_report(synthesis: Synthesis) -> dict:
    """Publish scenario scores separately from operational recommendations and alerts."""
    return {
        "evidence_mode": synthesis.evidence_mode,
        "decision_usable": False,
        "summary": synthesis.summary,
        "factors": [
            {
                "name": factor.name,
                "description": factor.description,
                "severity": factor.severity,
                "simulation_score": round(factor.confidence, 4),
            }
            for factor in synthesis.factors
        ],
        "recommendations": [],
        "confidence": None,
        "simulation_score": round(synthesis.confidence, 4),
        "alert_level": None,
        "factor_count": len(synthesis.factors),
    }


def generate_markdown_report(synthesis: Synthesis) -> str:
    """Arabic training report, including its evidence status when exported alone."""
    lines = [
        "# محاكاة بحث زراعي",
        "",
        "## الملخّص",
        "",
        synthesis.summary,
        "",
        "## العوامل في السيناريو",
        "",
    ]
    for factor in synthesis.factors:
        lines.extend([f"### {factor.name}", "", factor.description, ""])
    if not synthesis.factors:
        lines.append("لا تتوافر عوامل في هذا السيناريو.")
    lines.extend(
        [
            "",
            "## التوصيات الميدانية",
            "",
            "تحتاج التوصية إلى قياسات حقلية موثّقة.",
            "",
            "## مستوى الثقة الميداني",
            "",
            "غير مقدّر.",
        ]
    )
    return "\n".join(lines)


def generate_map_data(synthesis: Synthesis, region: str | None = None) -> dict:
    """Query region text carries no surveyed field or collection coordinates."""
    return {
        "type": "FeatureCollection",
        "features": [],
        "evidence_mode": synthesis.evidence_mode,
        "decision_usable": False,
        "geometry_status": "no_field_coordinates",
        "query_region": region,
    }
