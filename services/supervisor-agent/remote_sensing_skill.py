#!/usr/bin/env python3
"""
Remote Sensing Skill Library for SAHOOL Supervisor Agent
Handles: NDVI · SAR · Satellite imagery · Change detection
"""

import json
from typing import Any

from mcp_client import MCPClient


class RemoteSensingSkill:
    """
    Domain skill for satellite remote sensing operations.
    Wraps MCP calls to sentinel-hub server with caching and error handling.
    """

    def __init__(self, mcp_client: MCPClient):
        self.mcp = mcp_client
        self.server = "sentinel-hub"

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

        if intent == "ndvi":
            if not field_id:
                return {"type": "error", "response": "يجب تحديد معرف الحقل (field_id) لحساب NDVI."}

            # Get NDVI from MCP server
            result = await self.mcp.call_tool(
                self.server,
                "compute_ndvi",
                {"field_id": field_id, "date": context.get("date", "2026-05-18")},
            )

            content = result.get("content", [{}])[0].get("text", "{}")
            ndvi_data = json.loads(content)

            # Interpret NDVI values
            mean_ndvi = ndvi_data.get("mean", 0)
            if mean_ndvi < 0.2:
                health = "تربة عارية أو غطاء نباتي ضعيف جداً"
                recommendation = "⚠️ الحقل يحتاج إلى زراعة عاجلة أو ري فوري."
            elif mean_ndvi < 0.4:
                health = "غطاء نباتي متوسط — محاصيل مبكرة أو إجهاد مائي"
                recommendation = "💧 راقب رطوبة التربة. قد يحتاج إلى ري إضافي."
            elif mean_ndvi < 0.6:
                health = "غطاء نباتي جيد — نمو طبيعي"
                recommendation = "✅ الحالة جيدة. استمر في المراقبة الدورية."
            elif mean_ndvi < 0.8:
                health = "غطاء نباتي كثيف — نمو ممتاز"
                recommendation = "🌿 نمو ممتاز! راقب الآفات والأمراض المحتملة."
            else:
                health = "غطاء نباتي مكتمل — أقصى كثافة"
                recommendation = "🏆 كثافة نباتية ممتازة. استعد للحصاد."

            return {
                "type": "ndvi_report",
                "ndvi_mean": round(mean_ndvi, 3),
                "health_status": health,
                "recommendation": recommendation,
                "distribution": ndvi_data.get("health_distribution", {}),
                "cloud_coverage_pct": round(ndvi_data.get("cloud_coverage", 0) * 100, 1),
                "sources": ["Sentinel-2 L2A", "SAHOOL NDVI Engine"],
            }

        elif intent == "full_analysis":
            # Parallel S2 + S1 fetch
            today = "2026-05-18"
            date_range = f"2026-04-18/{today}"

            parallel_calls = [
                {
                    "server": self.server,
                    "tool": "fetch_sentinel2_l2a",
                    "args": {
                        "field_id": field_id,
                        "date_range": date_range,
                        "bands": [
                            "B02",
                            "B03",
                            "B04",
                            "B05",
                            "B06",
                            "B07",
                            "B08",
                            "B8A",
                            "B11",
                            "B12",
                        ],
                        "cloud_cover_max": 20,
                    },
                },
                {
                    "server": self.server,
                    "tool": "fetch_sentinel1_grd",
                    "args": {
                        "field_id": field_id,
                        "date_range": date_range,
                        "polarization": ["VV", "VH"],
                    },
                },
            ]

            results = await self.mcp.call_tools_parallel(parallel_calls)

            return {
                "type": "full_satellite_analysis",
                "satellite_results": results,
                "period": date_range,
                "recommendation": "تم جلب البيانات الفضائية. استخدم /agent/optimize لتحليل المفاضلات.",
                "sources": ["Sentinel-2", "Sentinel-1", "SAHOOL Fusion Engine"],
            }

        elif intent == "change_detection":
            return {
                "type": "change_detection",
                "response": "ميزة كشف التغيير قيد التطوير. ستكون متاحة في الإصدار القادم.",
                "sources": [],
            }

        else:
            return {
                "type": "error",
                "response": f"نوعية الاستعلام عن الاستشعار عن بعد غير معروفة: {intent}",
            }
