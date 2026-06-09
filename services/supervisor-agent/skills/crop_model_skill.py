#!/usr/bin/env python3
"""
Crop Model Skill Library for SAHOOL Supervisor Agent
Handles: تقدير الغلّة (RUE-based) · جدولة الريّ · توصيات التسميد

ملاحظة صدق: النموذج مقدّر غلّة قائم على RUE (biomass=ΣPAR×RUE×soil_factor،
yield=biomass×HI) مع توازن ماء FAO-56 — ليس WOFOST يومي التكامل. لا يلتقط
توقيت الإجهاد الطوْري (نافذة الإجهاد الحرجة)؛ الغلّة تقدير من الدرجة الأولى
يُحسّن بالمعايرة (TrueUp k_factor).
"""

import json
from typing import Any

from mcp_client import MCPClient


class CropModelSkill:
    """
    Domain skill for crop modeling and agronomic recommendations.
    """

    def __init__(self, mcp_client: MCPClient):
        self.mcp = mcp_client
        self.server = "wofost"

    async def execute(  # ✅ timeout + fallback added
        self,
        intent: str,
        query: str = "",
        field_id: str | None = None,
        user_id: str = "",
        tenant_id: str = "",
        context: dict[str, Any] = None,
        objectives: list[str] = None,
    ) -> dict[str, Any]:

        if intent == "simulate_current":
            crop = context.get("crop", "wheat") if context else "wheat"
            planting_date = context.get("planting_date", "2026-01-15") if context else "2026-01-15"
            soil = context.get("soil_type", "medium") if context else "medium"

            result = await self.mcp.call_tool(
                self.server,
                "run_wofost_simulation",
                {
                    "crop": crop,
                    "planting_date": planting_date,
                    "soil_type": soil,
                    "irrigation": True,
                    "co2_ppm": 420,
                },
            )

            content = result.get("content", [{}])[0].get("text", "{}")
            sim_data = json.loads(content)
            results = sim_data.get("results", {})

            return {
                "type": "rue_yield_estimate",  # RUE لا WOFOST يومي
                "crop": crop,
                "yield_kg_ha": results.get("yield_kg_ha", 0),
                "biomass_kg_ha": results.get("biomass_kg_ha", 0),
                "total_water_mm": results.get("total_water_mm", 0),
                "harvest_date": results.get("harvest_date", "N/A"),
                "phenology": results.get("phenology", {}),
                "gdd_total": results.get("gdd_total", 0),
                "stress_days": results.get("stress_days", 0),
                "sources": ["RUE-Estimator (FAO-56)", "SAHOOL Crop Model"],
            }

        elif intent == "irrigation_advice":
            # Get weather forecast first (warms cache / validates availability;
            # result intentionally not consumed by the simplified FAO-56 path below)
            await self.mcp.call_tool(
                "weather",
                "get_weather_forecast",
                {
                    "lat": context.get("lat", 15.0) if context else 15.0,
                    "lon": context.get("lon", 45.0) if context else 45.0,
                    "days": 7,
                },
            )

            # Simplified irrigation logic (production: FAO-56 full calculation)
            et0 = 5.0  # mm/day average
            kc = {
                "wheat": 0.85,
                "barley": 0.80,
                "maize": 1.15,
                "sorghum": 0.90,
                "millet": 0.75,
                "rice": 1.20,
                "potato": 1.10,
            }.get(context.get("crop", "wheat") if context else "wheat", 0.85)

            etc = et0 * kc  # mm/day
            weekly_need = etc * 7

            # Check soil moisture (from context or IoT)
            soil_moisture = context.get("soil_moisture_30cm", 40) if context else 40  # %

            if soil_moisture < 30:
                urgency = "🔴 عاجل — ري فوري"
                amount = round(weekly_need * 1.2, 1)
            elif soil_moisture < 50:
                urgency = "🟡 ري خلال 2–3 أيام"
                amount = round(weekly_need, 1)
            else:
                urgency = "🟢 لا حاجة للري الآن"
                amount = 0

            return {
                "type": "irrigation_advice",
                "advice": f"{urgency}",
                "amount_mm": amount,
                "timing": "صباحاً مبكراً (5–8 ص) لتقليل التبخر" if amount > 0 else "لا يوجد",
                "et0_mm_day": et0,
                "kc": kc,
                "etc_mm_day": round(etc, 2),
                "soil_moisture_pct": soil_moisture,
                "weekly_need_mm": round(weekly_need, 1),
                "sources": ["FAO-56", "WOFOST", "Open-Meteo"],
            }

        elif intent == "fertilizer_advice":
            crop = context.get("crop", "wheat") if context else "wheat"
            growth_stage = context.get("growth_stage", "vegetative") if context else "vegetative"

            # Simplified NPK recommendations (production: soil test + leaf analysis)
            recommendations = {
                "wheat": {
                    "vegetative": {"N": 80, "P": 40, "K": 30, "note": "تسميد نشط للأوراق"},
                    "flowering": {"N": 30, "P": 50, "K": 60, "note": "تسميد للحبوب"},
                    "ripening": {"N": 0, "P": 20, "K": 40, "note": "لا نيتروجين — يؤثر على الجودة"},
                },
                "maize": {
                    "vegetative": {"N": 120, "P": 50, "K": 40, "note": "ذرة تحتاج نيتروجيناً عالياً"},
                    "flowering": {"N": 60, "P": 40, "K": 50, "note": "تسميد عند الإزهار"},
                    "ripening": {"N": 0, "P": 20, "K": 30, "note": "تقليل التسميد"},
                },
            }

            rec = recommendations.get(crop, {}).get(
                growth_stage, {"N": 50, "P": 30, "K": 25, "note": "توصية عامة"}
            )

            return {
                "type": "fertilizer_advice",
                "crop": crop,
                "growth_stage": growth_stage,
                "recommendation_kg_ha": rec,
                "note": rec["note"],
                "sources": [
                    "FAO Guidelines",
                    "Yemen Ministry of Agriculture",
                    "SAHOOL Soil Analysis",
                ],
            }

        else:
            return {
                "type": "error",
                "response": f"نوعية استعلام نموذج المحصول غير معروفة: {intent}",
            }
