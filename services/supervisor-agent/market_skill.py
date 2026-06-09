#!/usr/bin/env python3
"""
Market Skill Library for SAHOOL Supervisor Agent
Handles: Price queries · Forward contracts · Trend analysis
"""

import json
from typing import Any

from mcp_client import MCPClient


class MarketSkill:
    """
    Domain skill for agricultural market operations.
    """

    def __init__(self, mcp_client: MCPClient):
        self.mcp = mcp_client
        self.server = "market"

    async def execute(
        self,
        intent: str,
        query: str = "",
        field_id: str | None = None,
        user_id: str = "",
        tenant_id: str = "",
        context: dict[str, Any] = None,
        objectives: list[str] = None,
    ) -> dict[str, Any]:

        if intent == "price_current":
            crop = context.get("crop", "wheat") if context else "wheat"
            market = context.get("market", "sanaa") if context else "sanaa"

            result = await self.mcp.call_tool(
                self.server, "get_market_price", {"crop": crop, "market": market}
            )

            content = result.get("content", [{}])[0].get("text", "{}")
            price_data = json.loads(content)

            return {
                "type": "price_current",
                "crop": crop,
                "market": market,
                "price_yer_kg": price_data.get("price_yer_kg", 0),
                "price_usd_kg": price_data.get("price_usd_kg", 0),
                "trend": price_data.get("trend", "stable"),
                "updated": price_data.get("updated", "N/A"),
                "sources": [f"SAHOOL Market Data — {market}"],
            }

        elif intent == "price_forecast":
            crop = context.get("crop", "wheat") if context else "wheat"

            result = await self.mcp.call_tool(self.server, "get_price_trend", {"crop": crop})

            content = result.get("content", [{}])[0].get("text", "{}")
            trend_data = json.loads(content)

            return {
                "type": "price_forecast",
                "crop": crop,
                "current_price_yer_kg": trend_data.get("current_price", 0),
                "change_30d_pct": trend_data.get("price_change_pct", 0),
                "forecast": trend_data.get("forecast", "stable"),
                "trend_data": trend_data.get("trend_data", [])[:7],  # Last 7 days
                "sources": ["SAHOOL Market Analytics"],
            }

        elif intent == "create_contract":
            if not field_id:
                return {"type": "error", "response": "يجب تحديد الحقل لإنشاء عقد آجل."}

            crop = context.get("crop", "wheat") if context else "wheat"
            yield_est = context.get("estimated_yield_kg", 1000) if context else 1000
            harvest = context.get("harvest_date", "2026-09-01") if context else "2026-09-01"

            result = await self.mcp.call_tool(
                self.server,
                "create_forward_contract",
                {
                    "farmer_id": user_id,
                    "field_id": field_id,
                    "crop": crop,
                    "estimated_yield_kg": yield_est,
                    "harvest_date": harvest,
                    "quality_grade": "A",
                },
            )

            content = result.get("content", [{}])[0].get("text", "{}")
            contract = json.loads(content)

            return {
                "type": "contract_created",
                "contract_id": contract.get("contract_id", "N/A"),
                "crop": crop,
                "yield_kg": yield_est,
                "price_yer_kg": contract.get("agreed_price_yer_kg", 0),
                "total_value_yer": contract.get("total_contract_value_yer", 0),
                "harvest_date": harvest,
                "status": contract.get("status", "pending"),
                "next_steps": contract.get("next_steps", []),
                "sources": ["SAHOOL B2B Marketplace"],
            }

        else:
            return {"type": "error", "response": f"نوعية استعلام السوق غير معروفة: {intent}"}
