#!/usr/bin/env python3
"""
Remote Sensing Skill Library for SAHOOL Supervisor Agent
Handles: NDVI · SAR · Satellite imagery · Change detection
"""

import json
import os
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
                "read_indicator_observation",
                {
                    "field_id": field_id,
                    "tenant_id": tenant_id,
                    "index": "ndvi",
                    "date": (context or {}).get("date", "latest"),
                },
            )

            content = result.get("content", [{}])[0].get("text", "{}")
            ndvi_data = json.loads(content)

            # Interpret NDVI values
            mean_ndvi = ndvi_data.get("mean")
            if mean_ndvi is None:
                return {"type": "error", "response": "لا توجد مشاهدة NDVI موثقة قابلة للاستخدام."}
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
                "scene_id": ndvi_data.get("scene_id"),
                "acquisition_date": ndvi_data.get("date"),
                "quality": ndvi_data.get("quality"),
                "sources": ["raster-service", "Sentinel-2 L2A"],
            }

        elif intent == "full_analysis":
            # Direct provider fetch is quarantined. The default brain reads persisted,
            # governed Raster products rather than bypassing product ownership.
            if os.getenv("BRAIN_DIRECT_SATELLITE_FETCH_ENABLED", "false").lower() not in {
                "1",
                "true",
                "yes",
            }:
                return {
                    "type": "governance_block",
                    "response": "الجلب المباشر من المزود معطل؛ استخدم منتجات raster-service الموثقة.",
                    "owner": "raster-service",
                }
            # Parallel S2 + S1 fetch (legacy opt-in only)
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
                "recommendation": "تم جلب البيانات الفضائية. استخدم /v1/agent/optimize لتحليل المفاضلات.",
                "sources": ["Sentinel-2", "Sentinel-1", "SAHOOL Fusion Engine"],
            }

        elif intent == "change_detection":
            # كشف التغيير المكاني (per-pixel 2D) — متاح فعليّاً عبر raster-service.
            # المسار الصادق: العامل يحسب شبكتي المؤشّر للتاريخين من COG (rasterio)
            # عبر /v1/process، ثم يستدعي /v1/change/detect لخريطة فرق تُظهر «أين» تدهور
            # الحقل (لا فقط «هل» المتوسّط تغيّر — المتوسّط يُخفي التدهور الموضعي).
            return {
                "type": "change_detection",
                "capability": "available",
                "endpoint": "POST /v1/change/detect (raster-service)",
                "required_inputs": {
                    "field_id": field_id,
                    "index": "ndvi|ndmi|salinity",
                    "date_before": "YYYY-MM-DD",
                    "date_after": "YYYY-MM-DD",
                    "grid_before": "شبكة المؤشّر للتاريخ الأقدم (من /v1/process)",
                    "grid_after": "شبكة المؤشّر للتاريخ الأحدث (من /v1/process)",
                },
                "recommendation": (
                    "احسب شبكتي المؤشّر للتاريخين عبر /v1/process ثمّ استدعِ "
                    "/v1/change/detect للحصول على خريطة فرق بكسل-بكسل ونسب المساحة "
                    "المتدهورة (تكشف الرقع الموضعيّة التي يُخفيها المتوسّط الزمني)."
                ),
                "sources": ["SAHOOL raster-service /v1/change/detect"],
            }

        else:
            return {
                "type": "error",
                "response": f"نوعية الاستعلام عن الاستشعار عن بعد غير معروفة: {intent}",
            }
