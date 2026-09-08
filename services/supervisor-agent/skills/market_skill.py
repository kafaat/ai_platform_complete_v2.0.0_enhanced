#!/usr/bin/env python3
"""Observed market data; missing prices and unavailable contracts stay explicit."""

import json
import math
from typing import Any

from mcp_client import MCPClient


class MarketSkill:
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
        if intent == "create_contract":
            # The owner explicitly returns 501. Do not claim a write succeeded,
            # invent harvest/yield/prices, or issue a write before governance.
            return _unavailable("forward_contract_not_implemented")
        tools = {"price_current": "get_market_price", "price_forecast": "get_price_trend"}
        if intent not in tools:
            return {"type": "error", "response": f"نوعية استعلام السوق غير معروفة: {intent}"}
        context = context or {}
        crop = context.get("crop")
        if not crop:
            return _unavailable("crop_required")
        arguments = {"crop": crop}
        if intent == "price_current":
            if not context.get("market"):
                return _unavailable("market_required")
            arguments["market"] = context["market"]
        envelope = await self.mcp.call_tool(self.server, tools[intent], arguments)
        try:
            if envelope.get("isError"):
                raise ValueError("tool error")
            data = json.loads(envelope["content"][0]["text"])
            key = "price_usd" if intent == "price_current" else "current_price_usd"
            price = data[key]
            if isinstance(price, bool) or not isinstance(price, (float, int)):
                raise ValueError("price not numeric")
            if not math.isfinite(price) or price <= 0 or data.get("error"):
                raise ValueError("price not observed")
            if data.get("currency") != "USD" or not data.get(
                "sample_count" if intent == "price_current" else "observation_count"
            ):
                raise ValueError("missing provenance")
        except (KeyError, IndexError, TypeError, ValueError):
            return _unavailable("market_observations_unavailable")
        historical = intent == "price_forecast"
        return {
            "type": "price_history" if historical else "price_current",
            "response": (
                "المتاح سجل أسعار تاريخي، ولا يتوفر نموذج توقع للسعر المستقبلي. "
                if historical
                else ""
            )
            + f"السعر المرصود: {price} دولار. وحدة التسعير غير مسجلة؛ لا يُفترض أنه سعر الكيلوغرام.",
            "structured": {"crop": crop, **data, "forecast_available": False},
            "actionable": False,
            "sources": ["SAHOOL market price observations"],
        }


def _unavailable(reason: str) -> dict:
    return {
        "type": "unavailable",
        "response": "لا تتوفر بيانات سوق موثقة لهذا الطلب أو أن الوظيفة المطلوبة غير متاحة حالياً.",
        "structured": {"status": "unavailable", "reason": reason},
        "actionable": False,
        "sources": [],
    }
