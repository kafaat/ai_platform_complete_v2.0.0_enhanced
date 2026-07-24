#!/usr/bin/env python3
"""
SAHOOL Sentinel Hub MCP Server
OAuth 2.1 + Streamable HTTP + Idempotent Tools
"""

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from shared.oauth_middleware import require_scope
from shared.streamable_http import StreamableHTTPTransport

from shared.field_change_summary import InsufficientObservations, summarize_field_change
from shared.helpers import retry_request

app = FastAPI(title="SAHOOL Sentinel Hub MCP Server", version="2026.1")
# ✅ OTEL
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    logging.getLogger(__name__).debug("OTEL غير مثبّت (اختياري)")

IDEMPOTENCY_CACHE: dict[str, Any] = {}
CACHE_TTL_SECONDS = 300

SH_CLIENT_ID = os.getenv("SH_CLIENT_ID", "")
SH_CLIENT_SECRET = os.getenv("SH_CLIENT_SECRET", "")
SH_INSTANCE_ID = os.getenv("SH_INSTANCE_ID", "")
SH_BASE_URL = "https://services.sentinel-hub.com"
# FIX: اسم الخدمة الفعليّ sahool-vegetation-analysis (كان sahool-vegetation لا يُحلّ).
RASTER_SERVICE_URL = os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001").rstrip(
    "/"
)


def _relay_raster_status(resp: httpx.Response) -> None:
    """يترجم استجابة raster-service غير الناجحة إلى حالة صادقة للمستدعي بدل تسريب 500.

    راستر يعيد **424** حين لا COG/مشاهدات مؤهّلة — وهو سلوك fail-closed صحيح يجب أن يصل
    مُستدعي MCP كـ424 (لا مشاهدة موثوقة) لا كـ500 عامّ. سابقاً كان ``resp.raise_for_status()``
    يرفع ``httpx.HTTPStatusError`` غير مُلتقَط ⇒ FastAPI يترجمه 500 (يُلبِس الفشلَ الصادقَ رمزاً
    مُضلِّلاً). هنا نُبقي الدلالة: 424⇒424 · 404⇒404 · بقيّة 4xx⇒422 · 5xx/غيرها⇒502 (خطأ منبع)."""
    if resp.is_success:
        return
    code = resp.status_code
    if code == 424:
        raise HTTPException(424, detail="authoritative raster observation unavailable")
    if code == 404:
        raise HTTPException(404, detail="field not found in raster-service")
    if 400 <= code < 500:
        raise HTTPException(422, detail=f"raster-service rejected request (upstream {code})")
    raise HTTPException(502, detail="raster-service upstream error")


FIELD_REGISTRY = {
    "field_01": {
        "name": "حقل وادي سبأ",
        "lat": 15.05,
        "lon": 45.55,
        "area_ha": 23.5,
        "crop": "قمح صلب",
        "bbox": [45.50, 15.00, 45.60, 15.10],
    },
    "field_02": {
        "name": "حقل البيضاء الشمالي",
        "lat": 15.02,
        "lon": 45.58,
        "area_ha": 32.0,
        "crop": "شعير",
        "bbox": [45.53, 14.97, 45.63, 15.07],
    },
    "field_03": {
        "name": "حقل البيضاء الجنوبي",
        "lat": 14.98,
        "lon": 45.52,
        "area_ha": 18.7,
        "crop": "ذرة صفراء",
        "bbox": [45.47, 14.93, 45.57, 15.03],
    },
    "field_04": {
        "name": "حقل رداع الغربي",
        "lat": 14.92,
        "lon": 45.48,
        "area_ha": 41.3,
        "crop": "طماطم",
        "bbox": [45.43, 14.87, 45.53, 14.97],
    },
    "field_05": {
        "name": "حقل ذي السفال",
        "lat": 14.88,
        "lon": 45.60,
        "area_ha": 28.9,
        "crop": "قمح صلب",
        "bbox": [45.55, 14.83, 45.65, 14.93],
    },
    "field_06": {
        "name": "حقل عتمة الشرقي",
        "lat": 15.10,
        "lon": 45.62,
        "area_ha": 37.5,
        "crop": "شعير",
        "bbox": [45.57, 15.05, 45.67, 15.15],
    },
    "field_07": {
        "name": "حقل الرياشية",
        "lat": 15.00,
        "lon": 45.45,
        "area_ha": 22.1,
        "crop": "خضروات",
        "bbox": [45.40, 14.95, 45.50, 15.05],
    },
    "field_08": {
        "name": "حقل ذي ناعم",
        "lat": 14.85,
        "lon": 45.65,
        "area_ha": 45.0,
        "crop": "بطاطس",
        "bbox": [45.60, 14.80, 45.70, 14.90],
    },
}


class ToolInput(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class Sentinel2Request(BaseModel):
    field_id: str
    date_range: str
    bands: list[str] = Field(default=["B04", "B08", "B11", "B12"])
    cloud_cover_max: float = 20.0


class Sentinel1Request(BaseModel):
    field_id: str
    date_range: str
    polarization: list[str] = Field(default=["VV", "VH"])


class NDVIRequest(BaseModel):
    field_id: str
    date: str


async def get_field_bbox(field_id: str) -> tuple:
    field = FIELD_REGISTRY.get(field_id)
    if not field:
        raise HTTPException(404, f"Field {field_id} not found")
    bbox = field.get("bbox")
    if bbox and len(bbox) == 4:
        return tuple(bbox)
    lat = field.get("lat", 15.05)
    lon = field.get("lon", 45.55)
    delta = 0.05
    return (lon - delta, lat - delta, lon + delta, lat + delta)


async def fetch_sentinel_hub_token() -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await retry_request(
            client.post,
            f"{SH_BASE_URL}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": SH_CLIENT_ID,
                "client_secret": SH_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


def build_evalscript(bands: list[str]) -> str:
    band_list = ", ".join([f'"{b}"' for b in bands])
    return f"""
//VERSION=3
function setup() {{
    return {{input: [{band_list}, "SCL"], output: {{bands: {len(bands) + 1}}}}}
}}
function evaluatePixel(sample) {{
    if ([3,8,9].includes(sample.SCL)) return [{", ".join(["NaN"] * len(bands))}, sample.SCL];
    return [{", ".join([f"sample.{b}" for b in bands])}, sample.SCL];
}}
"""


@app.get("/mcp/v1/tools", dependencies=[Depends(require_scope("satellite:read"))])
async def list_tools() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": "fetch_sentinel2_l2a",
                "description": "جلب صور Sentinel-2 Level-2A (BOA) لحقل محدد مع معالجة السحب",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "field_id": {"type": "string"},
                        "date_range": {"type": "string"},
                        "bands": {
                            "type": "array",
                            "items": {
                                "enum": [
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
                                ]
                            },
                        },
                        "cloud_cover_max": {"type": "number", "default": 20},
                    },
                    "required": ["field_id", "date_range"],
                },
            },
            {
                "name": "fetch_sentinel1_grd",
                "description": "جلب بيانات Sentinel-1 GRD (VV/VH)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "field_id": {"type": "string"},
                        "date_range": {"type": "string"},
                        "polarization": {"type": "array", "items": {"enum": ["VV", "VH"]}},
                    },
                    "required": ["field_id", "date_range"],
                },
            },
            {
                "name": "read_indicator_observation",
                "description": "قراءة أحدث مشاهدة مؤشر موثقة من raster-service؛ لا يعيد الحساب داخل MCP",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "field_id": {"type": "string"},
                        "date": {"type": "string", "format": "date"},
                        "index": {"type": "string", "default": "ndvi"},
                        "tenant_id": {"type": "string"},
                    },
                    "required": ["field_id", "tenant_id"],
                },
            },
            {
                "name": "analyze_field_change",
                "description": (
                    "تلخيص تغيّر المؤشّر للحقل بين أوّل وآخر مشاهدة حقيقيّة (منذ تاريخ اختياريّ). "
                    "يقرأ السلسلة الزمنيّة القانونيّة من raster-service ويقارنها فقط — لا حساب "
                    "طيفيّ ولا تفسير زراعيّ (التفسير في decision-service). قراءة فقط."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "field_id": {"type": "string"},
                        "tenant_id": {"type": "string"},
                        "index": {"type": "string", "default": "ndvi"},
                        "since": {
                            "type": "string",
                            "format": "date",
                            "description": "YYYY-MM-DD — يقارن المشاهدات من هذا التاريخ فأحدث.",
                        },
                    },
                    "required": ["field_id", "tenant_id"],
                },
            },
        ]
    }


@app.post("/mcp/v1/tools/call", dependencies=[Depends(require_scope("satellite:read"))])
async def call_tool(request: Request):
    body = await request.json()
    tool_input = ToolInput(**body)
    if tool_input.request_id:
        cached = IDEMPOTENCY_CACHE.get(tool_input.request_id)
        if cached and datetime.now(UTC) < cached["expires_at"]:
            return cached["result"]
    result = await _execute_tool(tool_input)
    if tool_input.request_id:
        IDEMPOTENCY_CACHE[tool_input.request_id] = {
            "result": result,
            "expires_at": datetime.now(UTC) + timedelta(seconds=CACHE_TTL_SECONDS),
        }
    return result


async def _execute_tool(tool_input: ToolInput) -> dict[str, Any]:
    name = tool_input.name
    args = tool_input.arguments
    if name == "fetch_sentinel2_l2a":
        req = Sentinel2Request(**args)
        bbox = await get_field_bbox(req.field_id)
        token = await fetch_sentinel_hub_token()
        evalscript = build_evalscript(req.bands)
        payload = {
            "input": {
                "bounds": {
                    "bbox": list(bbox),
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
                },
                "data": [
                    {
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {
                                "from": req.date_range.split("/")[0] + "T00:00:00Z",
                                "to": req.date_range.split("/")[1] + "T23:59:59Z",
                            },
                            "maxCloudCoverage": req.cloud_cover_max,
                        },
                    }
                ],
            },
            "output": {"responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
            "evalscript": evalscript,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await retry_request(
                client.post,
                f"{SH_BASE_URL}/api/v1/process",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "status": "success",
                            "source": "Sentinel-2 L2A",
                            "bands": req.bands,
                            "bbox": bbox,
                            "cloud_cover_max": req.cloud_cover_max,
                            "data_size_bytes": len(resp.content),
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        }
    elif name == "fetch_sentinel1_grd":
        req = Sentinel1Request(**args)
        bbox = await get_field_bbox(req.field_id)
        token = await fetch_sentinel_hub_token()
        payload = {
            "input": {
                "bounds": {"bbox": list(bbox)},
                "data": [
                    {
                        "type": "sentinel-1-grd",
                        "dataFilter": {
                            "timeRange": {
                                "from": req.date_range.split("/")[0] + "T00:00:00Z",
                                "to": req.date_range.split("/")[1] + "T23:59:59Z",
                            },
                            "polarization": req.polarization,
                        },
                    }
                ],
            },
            "output": {"responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await retry_request(
                client.post,
                f"{SH_BASE_URL}/api/v1/process",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "status": "success",
                            "source": "Sentinel-1 GRD",
                            "polarization": req.polarization,
                            "bbox": bbox,
                            "data_size_bytes": len(resp.content),
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        }
    elif name in {"read_indicator_observation", "compute_ndvi"}:
        # ``compute_ndvi`` is a compatibility alias only. The MCP/brain never performs
        # spectral computation; it reads the authoritative Raster product.
        field_id = str(args.get("field_id") or "").strip()
        tenant_id = str(args.get("tenant_id") or "").strip()
        index = str(args.get("index") or "ndvi").strip().lower()
        date = str(args.get("date") or "latest").strip()
        if not field_id or not tenant_id:
            raise HTTPException(422, detail="field_id and tenant_id are required")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await retry_request(
                client.get,
                f"{RASTER_SERVICE_URL}/v1/fields/{field_id}/indicator-grid",
                params={"index": index, "date": date, "grid": 16},
                headers={"X-Tenant-Id": tenant_id},
                timeout=60.0,
            )
            _relay_raster_status(resp)  # 424 من راستر ⇒ 424 لا 500 (fail-closed صادق)
            data = resp.json()
        if not data.get("real_data") or data.get("source") == "simulation":
            raise HTTPException(424, detail="authoritative raster observation unavailable")
        stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
        payload = {
            "field_id": field_id,
            "tenant_id": tenant_id,
            "index": index,
            "mean": stats.get("mean"),
            "date": data.get("date"),
            "scene_id": data.get("scene_id") or data.get("asset_id"),
            "source": "raster-service",
            "real_data": True,
            "quality": data.get("quality") or data.get("quality_gate"),
            "deprecated_alias_used": name == "compute_ndvi",
        }
        return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}
    elif name == "analyze_field_change":
        # المسار 1 (MCP فوق CDSE): أداة مركَّبة قراءة-فقط. تقرأ السلسلة الزمنيّة
        # القانونيّة من raster-service وتُلخّص التغيّر عبر منطق نقيّ مشترك — لا حساب
        # طيفيّ في MCP، ولا كتابة (satellite:read)، ولا تفسير زراعيّ.
        field_id = str(args.get("field_id") or "").strip()
        tenant_id = str(args.get("tenant_id") or "").strip()
        index = str(args.get("index") or "ndvi").strip().lower()
        since = args.get("since")
        since = str(since).strip() if since else None
        if not field_id or not tenant_id:
            raise HTTPException(422, detail="field_id and tenant_id are required")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await retry_request(
                client.get,
                f"{RASTER_SERVICE_URL}/v1/fields/{field_id}/timeseries",
                params={"index": index},
                headers={"X-Tenant-Id": tenant_id},
            )
            _relay_raster_status(resp)  # 424 من راستر ⇒ 424 لا 500 (fail-closed صادق)
            data = resp.json()
        # صدق: raster-service يُعلن available=False بلا COG — لا نُخمّن مقارنةً.
        points = data.get("points") if data.get("available") else []
        try:
            summary = summarize_field_change(
                points or [],
                field_id=field_id,
                tenant_id=tenant_id,
                index=index,
                since=since,
            )
        except InsufficientObservations as exc:
            raise HTTPException(424, detail=str(exc)) from exc
        return {"content": [{"type": "text", "text": json.dumps(summary, ensure_ascii=False)}]}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {name}")


transport = StreamableHTTPTransport(app, path="/mcp/v1/stream")


@app.get("/healthz")
@app.get("/health")
async def healthz():
    return {"status": "alive"}


@app.get("/readyz")
async def readyz():
    return {"status": "ready"}


import signal as _signal  # noqa: E402


def _handle_sigterm(signum, frame):
    """Graceful shutdown on SIGTERM."""
    import sys

    sys.exit(0)


_signal.signal(_signal.SIGTERM, _handle_sigterm)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
