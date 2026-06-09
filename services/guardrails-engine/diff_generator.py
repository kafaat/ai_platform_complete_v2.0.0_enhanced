#!/usr/bin/env python3
"""
Action Diff Generator for SAHOOL Guardrails
Generates comparison between rejected action and safe alternative.
"""

from typing import Any


class ActionDiffGenerator:
    """
    Generates human-readable diffs showing what needs to change
    for a rejected action to become safe.
    """

    async def generate(
        self, original: dict, checks: list[dict], farm_context: dict
    ) -> dict[str, Any]:
        """
        Generate diff between original (rejected) and safe alternative.
        """
        safe_alternative = dict(original)
        changes = []

        for check in checks:
            if check.get("passed", True):
                continue

            for suggestion in check.get("suggestions", []):
                field = suggestion.get("field", "")
                current_value = original.get(field)
                suggested_value = suggestion.get("value")

                if field and suggested_value is not None:
                    safe_alternative[field] = suggested_value

                    changes.append(
                        {
                            "field": field,
                            "current": current_value,
                            "suggested": suggested_value,
                            "reason_en": suggestion.get("text", ""),
                            "reason_ar": suggestion.get("text_ar", ""),
                            "tier": check.get("tier", "unknown"),
                            "severity": self._get_severity_for_field(check, field),
                        }
                    )

            # Handle special cases (e.g., banned chemical → suggest alternative)
            for finding in check.get("findings", []):
                if finding.get("rule") == "banned_substance":
                    # Suggest organic alternative
                    changes.append(
                        {
                            "field": "chemical",
                            "current": original.get("chemical"),
                            "suggested": "organic_alternative",
                            "reason_en": "Banned substance — use organic alternative",
                            "reason_ar": "مادة محظورة — استخدم بديلاً عضوياً",
                            "tier": "chemical",
                            "severity": "CRITICAL",
                            "organic_alternatives": self._suggest_organic_alternative(
                                original.get("chemical", ""),
                                original.get("crop", ""),
                                original.get("pest_target", ""),
                            ),
                        }
                    )
                    safe_alternative["chemical"] = "organic_alternative"

        # Calculate impact of changes
        impact = self._calculate_impact(original, safe_alternative, changes, farm_context)

        return {
            "original_action": original,
            "safe_alternative": safe_alternative,
            "changes": changes,
            "impact": impact,
            "diff_summary_ar": self._generate_arabic_summary(changes, impact),
            "diff_summary_en": self._generate_english_summary(changes, impact),
        }

    def _get_severity_for_field(self, check: dict, field: str) -> str:
        """Get highest severity for a field from check findings."""
        severities = [f.get("severity", "LOW") for f in check.get("findings", [])]
        if "CRITICAL" in severities:
            return "CRITICAL"
        elif "HIGH" in severities:
            return "HIGH"
        elif "MEDIUM" in severities:
            return "MEDIUM"
        return "LOW"

    def _suggest_organic_alternative(
        self, banned_chemical: str, crop: str, pest_target: str
    ) -> list[str]:
        """Suggest organic alternatives for banned chemicals."""
        alternatives = {
            "methyl_bromide": ["Biofumigation with mustard cover crops", "Solarization"],
            "ddt": ["Neem oil spray", "Biological control (Trichogramma wasps)"],
            "paraquat": ["Flame weeding", "Mechanical cultivation", "Mulching"],
            "endosulfan": ["Neem oil (Azadirachtin)", "Spinosad", "Bacillus thuringiensis"],
            "chlorpyrifos": ["Neem oil", "Pyrethrin (organic)", "Predatory insects"],
            "glyphosate": ["Mechanical weeding", "Flame weeding", "Cover crops (smothering)"],
        }

        return alternatives.get(
            banned_chemical, ["Consult local agricultural extension for organic alternatives"]
        )

    def _calculate_impact(
        self, original: dict, safe: dict, changes: list[dict], farm_context: dict
    ) -> dict:
        """Calculate economic and agronomic impact of adopting safe alternative."""
        # Cost impact
        original_cost = original.get("cost_usd", 0)
        safe_cost = safe.get("cost_usd", original_cost)

        # For dosage reductions, cost usually decreases
        cost_change_pct = (
            ((safe_cost - original_cost) / original_cost * 100) if original_cost > 0 else 0
        )

        # Yield impact estimate (simplified)
        original_yield = original.get(
            "projected_yield_kg_ha", farm_context.get("expected_yield_kg_ha", 2000)
        )
        safe_yield = original_yield * 0.95  # Conservative: 5% yield reduction for safer methods

        yield_change_pct = (
            ((safe_yield - original_yield) / original_yield * 100) if original_yield > 0 else 0
        )

        # Safety score improvement
        original_risk_score = len([c for c in changes if c["severity"] in ["CRITICAL", "HIGH"]])
        safe_risk_score = 0  # By definition, safe alternative passes all checks

        return {
            "cost_change_usd": round(safe_cost - original_cost, 2),
            "cost_change_pct": round(cost_change_pct, 1),
            "yield_change_kg_ha": round(safe_yield - original_yield, 2),
            "yield_change_pct": round(yield_change_pct, 1),
            "risk_reduction": original_risk_score,
            "safety_score_original": max(0, 10 - original_risk_score * 2),
            "safety_score_safe": max(0, 10 - safe_risk_score * 2),
            "net_benefit_score": round(
                (10 - max(0, 10 - original_risk_score * 2)) * 0.5
                + (-cost_change_pct if cost_change_pct < 0 else 0) * 0.3
                + (-yield_change_pct if yield_change_pct < 0 else 0) * 0.2,
                2,
            ),
        }

    def _generate_arabic_summary(self, changes: list[dict], impact: dict) -> str:
        """Generate Arabic summary of diff."""
        lines = ["📋 **ملخص التعديلات المطلوبة:**", ""]

        for i, change in enumerate(changes, 1):
            severity_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(
                change["severity"], "⚪"
            )
            lines.append(f"{severity_emoji} **{i}.** {change['reason_ar']}")
            lines.append(f"   الحالي: `{change['current']}` → المقترح: `{change['suggested']}`")

            if "organic_alternatives" in change:
                lines.append(
                    f"   🌿 **بدائل عضوية:** {', '.join(change['organic_alternatives'][:2])}"
                )
            lines.append("")

        lines.append("📊 **تأثير التعديلات:**")
        lines.append(
            f"• التكلفة: {'تنخفض' if impact['cost_change_pct'] <= 0 else 'ترتفع'} بـ {abs(impact['cost_change_pct'])}%"
        )
        lines.append(
            f"• الإنتاجية: {'تنخفض' if impact['yield_change_pct'] <= 0 else 'ترتفع'} بـ {abs(impact['yield_change_pct'])}%"
        )
        lines.append(
            f"• السلامة: تحسن من {impact['safety_score_original']}/10 إلى {impact['safety_score_safe']}/10"
        )
        lines.append(f"• صافي الفائدة: {impact['net_benefit_score']}")

        return "\n".join(lines)

    def _generate_english_summary(self, changes: list[dict], impact: dict) -> str:
        """Generate English summary of diff."""
        lines = ["📋 **Required Modifications Summary:**", ""]

        for i, change in enumerate(changes, 1):
            severity_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(
                change["severity"], "⚪"
            )
            lines.append(f"{severity_emoji} **{i}.** {change['reason_en']}")
            lines.append(f"   Current: `{change['current']}` → Suggested: `{change['suggested']}`")
            lines.append("")

        lines.append("📊 **Impact of Modifications:**")
        lines.append(
            f"• Cost: {'decreases' if impact['cost_change_pct'] <= 0 else 'increases'} by {abs(impact['cost_change_pct'])}%"
        )
        lines.append(
            f"• Yield: {'decreases' if impact['yield_change_pct'] <= 0 else 'increases'} by {abs(impact['yield_change_pct'])}%"
        )
        lines.append(
            f"• Safety: improves from {impact['safety_score_original']}/10 to {impact['safety_score_safe']}/10"
        )

        return "\n".join(lines)
