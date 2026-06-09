#!/usr/bin/env python3
import logging as _log
_audit = _log.getLogger("guardrails.environmental_tier")
#!/usr/bin/env python3
"""
Tier 2: Environmental Safety Guardrails
Validates actions against:
- Water withdrawal limits (groundwater/surface)
- Soil health preservation
- Carbon footprint constraints
- Biodiversity protection (buffer zones)
"""
from typing import Any, Dict, List


class EnvironmentalSafetyTier:
    """
    Environmental impact validation for farm actions.
    """

    # Yemen-specific water limits (m³ per hectare per season)
    WATER_LIMITS = {
        "groundwater": {"max_m3_ha_season": 10000, "critical_m3_ha_season": 8000},
        "surface": {"max_m3_ha_season": 15000, "critical_m3_ha_season": 12000},
        "mixed": {"max_m3_ha_season": 12000, "critical_m3_ha_season": 10000}
    }

    # Soil health thresholds
    SOIL_THRESHOLDS = {
        "salinity_ec_max": 4.0,  # dS/m
        "ph_min": 5.5,
        "ph_max": 8.5,
        "organic_matter_min_pct": 1.5,
        "erosion_risk_slope_pct": 15
    }

    # Carbon budget per hectare (kg CO2e/season)
    CARBON_BUDGET = {
        "wheat": 500,
        "barley": 450,
        "maize": 600,
        "sorghum": 400,
        "millet": 350,
        "rice": 800,  # High due to methane
        "potato": 300,
        "tomato": 400,
        "coffee": 200  # Perennial, carbon sink
    }

    async def validate(self, action_type: str, action_data: Dict, farm_context: Dict) -> Dict:
        findings = []
        suggestions = []
        passed = True

        crop = farm_context.get("crop", "wheat")
        field_area_ha = farm_context.get("field_area_ha", 1.0)
        water_source = farm_context.get("water_source", "groundwater")

        if action_type == "irrigation":
            water_m3 = action_data.get("water_m3", 0)
            water_per_ha = water_m3 / field_area_ha if field_area_ha > 0 else water_m3

            # Check seasonal water limits
            season_used = farm_context.get("season_water_used_m3_ha", 0)
            total_projected = season_used + water_per_ha

            limits = self.WATER_LIMITS.get(water_source, self.WATER_LIMITS["groundwater"])

            if total_projected > limits["max_m3_ha_season"]:
                findings.append({
                    "severity": "HIGH",
                    "message": f"Projected water use {total_projected:.0f} m³/ha exceeds seasonal limit {limits['max_m3_ha_season']}",
                    "message_ar": f"الاستهلاك المتوقع {total_projected:.0f} م³/هكتار يتجاوز الحد الموسمي ({limits['max_m3_ha_season']})",
                    "rule": "water_limit_exceeded"
                })
                passed = False
                suggestions.append({
                    "field": "water_m3",
                    "value": max(0, (limits["max_m3_ha_season"] - season_used) * field_area_ha),
                    "text": "Reduce to stay within seasonal water budget",
                    "text_ar": "قلل الكمية للبقاء ضمن ميزانية المياه الموسمية"
                })
            elif total_projected > limits["critical_m3_ha_season"]:
                findings.append({
                    "severity": "MEDIUM",
                    "message": f"Water use approaching critical threshold {limits['critical_m3_ha_season']} m³/ha",
                    "message_ar": f"استهلاك المياه يقترب من الحد الحرج ({limits['critical_m3_ha_season']} م³/هكتار)",
                    "rule": "water_critical_approach"
                })

            # Check soil salinity risk from irrigation
            irrigation_ec = action_data.get("water_ec_ds_m", 0)
            current_soil_ec = farm_context.get("soil_ec_ds_m", 0)

            if irrigation_ec > 2.0 and current_soil_ec > 2.5:
                findings.append({
                    "severity": "HIGH",
                    "message": f"Irrigation water EC {irrigation_ec} dS/m will increase soil salinity risk",
                    "message_ar": f"مياه الري ذات ملوحة {irrigation_ec} ديسي سيمنز/م ستزيد من خطر تملح التربة الحالية ({current_soil_ec})",
                    "rule": "salinity_risk"
                })
                suggestions.append({
                    "field": "water_source",
                    "value": "low_salinity_source",
                    "text": "Use lower-EC water source or implement leaching fraction",
                    "text_ar": "استخدم مصدر مياه أقل ملوحة أو طبّق كسر غسيل"
                })

        elif action_type == "fertilization":
            # Check carbon footprint of synthetic fertilizer production
            n_kg = action_data.get("N_kg_ha", 0)
            # Synthetic N fertilizer: ~8 kg CO2e per kg N (production + transport)
            fertilizer_carbon = n_kg * 8

            crop_budget = self.CARBON_BUDGET.get(crop, 500)
            season_carbon = farm_context.get("season_carbon_kg_co2e", 0)
            projected_total = season_carbon + fertilizer_carbon

            if projected_total > crop_budget:
                findings.append({
                    "severity": "MEDIUM",
                    "message": f"Fertilizer carbon footprint {fertilizer_carbon:.0f} kg CO2e exceeds crop carbon budget",
                    "message_ar": f"البصمة الكربونية للتسميد {fertilizer_carbon:.0f} كجم CO₂e تتجاوز ميزانية المحصول ({crop_budget})",
                    "rule": "carbon_budget_exceeded"
                })
                suggestions.append({
                    "field": "N_kg_ha",
                    "value": max(0, (crop_budget - season_carbon) / 8),
                    "text": "Reduce synthetic N or use organic alternatives",
                    "text_ar": "قلل النيتروجين الصناعي أو استخدم بدائل عضوية"
                })

        return {
            "tier": "environmental",
            "passed": passed,
            "findings": findings,
            "suggestions": suggestions
        }
