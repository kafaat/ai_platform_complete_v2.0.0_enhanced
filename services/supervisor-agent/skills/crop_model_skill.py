#!/usr/bin/env python3
"""
Crop Model Skill Library for SAHOOL Supervisor Agent
Handles: تقدير الغلّة (RUE-based) · جدولة الريّ · توصيات التسميد

ملاحظة صدق: النموذج مقدّر غلّة قائم على RUE (biomass=ΣPAR×RUE×soil_factor،
yield=biomass×HI) مع توازن ماء FAO-56 — ليس WOFOST يومي التكامل. لا يلتقط
توقيت الإجهاد الطوْري (نافذة الإجهاد الحرجة)؛ الغلّة تقدير من الدرجة الأولى
يُحسّن بالمعايرة (TrueUp k_factor).
"""

import asyncio
import json
import os
from typing import Any
from urllib.parse import quote

import httpx
from mcp_client import MCPClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError


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
            return await self._irrigation_advice(field_id, context or {})

        elif intent == "fertilizer_advice":
            # No approved soil-specific prescription is exposed by this skill yet.
            # Crop/stage templates cannot establish a safe nutrient dose.
            return _unavailable(
                "fertilizer_prescription_required",
                "توصية التسميد الكمية غير متاحة: يلزم تحليل تربة معتمد ووصفة تسميد مراجعة للحقل.",
            )

        else:
            return {
                "type": "error",
                "response": f"نوعية استعلام نموذج المحصول غير معروفة: {intent}",
            }

    async def _irrigation_advice(self, field_id: str | None, context: dict) -> dict:
        state = context.get("field_state") or {}
        bearer = context.get("_platform_bearer")
        if not field_id or not bearer or state.get("validity") != "valid":
            return _unavailable(
                "canonical_field_evidence_required",
                "لا يمكن تحديد كمية ري آمنة دون حقل محدد وبيانات حقل صالحة من المنصة.",
            )
        platform = os.getenv(
            "PLATFORM_SERVICE_URL", os.getenv("PLATFORM_URL", "http://sahool-platform:8000")
        ).rstrip("/")
        field_path = f"{platform}/api/v1/fields/{quote(str(field_id), safe='')}"
        # Delegate all ET0/Kc/rain calculations to the existing owner. Never
        # interpret missing observations as dry weather or invent soil moisture.
        async with httpx.AsyncClient(timeout=20.0) as client:
            headers = {"Authorization": f"Bearer {bearer}"}
            async with asyncio.timeout(20.0):
                advice_resp, field_resp = await asyncio.gather(
                    client.get(f"{field_path}/weather/irrigation-advice", headers=headers),
                    client.get(field_path, headers=headers),
                )
            advice_resp.raise_for_status()
            field_resp.raise_for_status()
            advice, field = advice_resp.json(), field_resp.json()
        try:
            if not isinstance(advice, dict) or not isinstance(field, dict):
                raise ValueError("invalid canonical payload")
            if advice.get("field_id") != field_id or field.get("field_id") != field_id:
                raise ValueError("field identity mismatch")
            evidence = _IrrigationInputs(
                water_mm=advice.get("recommended_mm"),
                area_ha=field.get("area_ha"),
                irrigation_efficiency_pct=field.get("irrigation_efficiency_pct"),
                field_id=field_id,
            )
            # The owner's recommendation is NET crop demand. Withdrawal limits
            # govern GROSS water: preserve both and apply only explicit canonical
            # field efficiency (ADR-0032); never assume an irrigation system's efficiency.
            net_water_m3 = evidence.water_mm * evidence.area_ha * 10
            action = IrrigationAction(
                **evidence.model_dump(),
                net_water_m3=net_water_m3,
                water_m3=net_water_m3 / evidence.irrigation_efficiency_pct * 100,
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ValidationError) and any(
                error["loc"] == ("irrigation_efficiency_pct",) for error in exc.errors()
            ):
                return _unavailable(
                    "canonical_irrigation_efficiency_required",
                    "كفاءة الري غير متاحة أو غير صالحة؛ لا يمكن حساب حجم السحب الإجمالي للتحقق من حدود المياه.",
                )
            return _unavailable(
                "canonical_irrigation_incomplete",
                "بيانات توصية الري أو مساحة الحقل غير مكتملة؛ لا يمكن إصدار كمية آمنة.",
            )
        return {
            "type": "irrigation_advice",
            "advice": advice.get("rationale_ar", ""),
            "amount_mm": action.water_mm,
            "timing": advice.get("timing_ar", "غير محدد"),
            "actionable": True,
            "action_type": "irrigation",
            "structured": action.model_dump(),
            "farm_context": {
                "field_id": field_id,
                "field_area_ha": action.area_ha,
                "water_source": field.get("water_source"),
                "field_state": state,
            },
            "sources": [
                "SAHOOL field irrigation advice",
                advice.get("source") or "weather-service",
            ],
        }


class _IrrigationInputs(BaseModel):
    """Explicit canonical inputs; missing efficiency cannot become full efficiency."""

    model_config = ConfigDict(strict=True, allow_inf_nan=False, extra="forbid")
    field_id: str
    water_mm: float = Field(ge=0, description="Net crop demand in mm")
    area_ha: float = Field(gt=0)
    irrigation_efficiency_pct: float = Field(gt=0, le=100)


class IrrigationAction(_IrrigationInputs):
    """Keep net crop demand separate from gross withdrawal sent to governance."""

    net_water_m3: float = Field(ge=0)
    water_m3: float = Field(ge=0, description="Gross withdrawal volume in m3")


def _unavailable(code: str, message: str) -> dict:
    return {
        "type": "unavailable",
        "response": message,
        "actionable": False,
        "structured": {"status": "unavailable", "reason": code},
        "sources": [],
    }
