#!/usr/bin/env python3
"""
SAHOOL Sentinel Hub MCP Server
OAuth 2.1 + Streamable HTTP + Idempotent Tools
"""

import json
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from shared.oauth_middleware import idempotency_key, require_scope
from shared.streamable_http import StreamableHTTPTransport

from shared.field_change_summary import InsufficientObservations, summarize_field_change
from shared.gis.phase5_runtime import geometry_bbox
from shared.helpers import retry_request
from shared.security.service_tenant_assertion import create_tenant_assertion
from shared.security.trusted_tenant import TrustedTenantError, resolve_trusted_tenant

app = FastAPI(title="SAHOOL Sentinel Hub MCP Server", version="2026.1")
# ✅ OTEL
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    logging.getLogger(__name__).debug("OTEL غير مثبّت (اختياري)")

IDEMPOTENCY_CACHE: dict[str, Any] = {}
CACHE_TTL_SECONDS = 300

# ── Copernicus Data Space (CDSE) — نقاط المنصّة نفسها لا Sentinel Hub التجاريّ ──────────
# العطلُ المقيس (التدقيق الحيّ 2026-09-29): العنوان كان ``services.sentinel-hub.com`` ثابتاً
# بينما الاعتمادات عميلُ OAuth على realm الـCDSE (``SH_TOKEN_URL`` في .env.example وcompose)،
# فكلُّ جلبٍ يطلب توكناً من مُصدِرٍ لا يعرف العميل. الأسماء والافتراضات هنا هي نفسها في
# المالك القانونيّ ``services/raster-service/cdse_client.py`` (``_TOKEN_URL``/``_BASE_URL``/
# ``_cdse_credentials``) — ويقيس الاختبارُ تطابقَها كي لا تنجرف نسختان.
SH_TOKEN_URL = os.getenv(
    "SH_TOKEN_URL",
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
)
SH_BASE_URL = os.getenv("SH_BASE_URL", "https://sh.dataspace.copernicus.eu").rstrip("/")
SERVICE_NAME = "sentinel-hub-mcp"
# FIX: اسم الخدمة الفعليّ sahool-vegetation-analysis (كان sahool-vegetation لا يُحلّ).
RASTER_SERVICE_URL = os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001").rstrip(
    "/"
)
# مالكُ جدول fields المُعلَن (docs/architecture/db_ownership.yml) — نفس عقد vegetation-analysis:
# توكن الخدمة + اسم المُنادي + ادّعاء مستأجِرٍ موقَّعٍ مربوطٍ بالطلب (service_tenant_assertion).
FIELD_SERVICE_URL = os.getenv("FIELD_SERVICE_URL", "").rstrip("/")


def _cdse_credentials() -> tuple[str, str]:
    """``CDSE_CLIENT_ID/SECRET`` مع ارتداد إلى ``SH_CLIENT_ID/SECRET`` — ترتيب raster-service."""
    cid = os.getenv("CDSE_CLIENT_ID") or os.getenv("SH_CLIENT_ID") or ""
    secret = os.getenv("CDSE_CLIENT_SECRET") or os.getenv("SH_CLIENT_SECRET") or ""
    return cid, secret


def _caller_tenant(user: dict, args: dict) -> str:
    """المستأجِر من التوكن المُتحقَّق وحدَه؛ ``tenant_id`` في الوسائط صدىً له أو رفض.

    العطلُ المقيس: ``read_indicator_observation``/``analyze_field_change`` كانا يمرّران
    ``args["tenant_id"]`` ترويسةً إلى raster-service، فحاملُ ``satellite:read`` لمستأجِرٍ يسمّي
    غيره. القاعدة نفسها في ``shared.security.trusted_tenant.resolve_trusted_tenant``: القيمة
    الموثَّقة تحكم، والمُدخَل يُطابقها أو يُرفَض (403)، لا يتجاوزها أبداً.
    """
    try:
        return resolve_trusted_tenant(user.get("tenant_id"), args.get("tenant_id"))
    except TrustedTenantError as exc:
        status = 403 if exc.code == "tenant_mismatch" else 401
        raise HTTPException(status, detail=exc.code) from exc


def _raster_headers(tenant_id: str) -> dict[str, str]:
    """raster-service يُصدّق X-Tenant-Id بجانب توكن الخدمة فقط (RASTER-TENANT-TRUST-01)؛ بلا
    توكنٍ مضبوط لا نُرسل ادّعاءً مجهول المصدر — 503 صادق بدل 401 من المنبع."""
    token = os.getenv("SAHOOL_AGENT_TOKEN", "")
    if not token:
        raise HTTPException(503, detail="SAHOOL_AGENT_TOKEN not configured")
    return {"X-Tenant-Id": tenant_id, "X-Agent-Token": token, "X-Service-Name": SERVICE_NAME}


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


async def get_field_bbox(field_id: str, tenant_id: str) -> tuple:
    """حدودُ الحقل من مالكه (field-management-service) للمستأجِر المُتحقَّق — لا سجلَّ تجريبيّاً.

    العطلُ المقيس: أداتا الجلب كانتا تحلّان ``field_id`` من ثمانية حقولٍ مكتوبة في الملفّ
    (``field_0N``) بحدودٍ مخترَعة، فيُرسَل bbox مختلَق إلى المزوّد لحقلٍ لا وجود
    له، وأيُّ حقلٍ حقيقيّ ⇒ 404. هنا عقدُ vegetation-analysis نفسه: ``GET /internal/fields/{id}``
    بتوكن الخدمة واسم المُنادي وادّعاء مستأجِرٍ موقَّعٍ مربوطٍ بالطريقة والمسار ومعرّف الطلب.
    غيابُ التهيئة أو تعذّر المالك ⇒ خطأٌ مُعلَن (503/502)، وحقلُ مستأجِرٍ آخر لا يُميَّز عن غائب
    (404) — ولا ارتدادَ إلى حدودٍ مخترَعة في أيّ فرع.
    """
    token = os.getenv("SAHOOL_AGENT_TOKEN", "")
    key = os.getenv("FIELD_SERVICE_TENANT_ASSERTION_KEY", "")
    if not (FIELD_SERVICE_URL and token and key):
        raise HTTPException(
            503,
            detail="field_source_unconfigured: FIELD_SERVICE_URL, SAHOOL_AGENT_TOKEN and "
            "FIELD_SERVICE_TENANT_ASSERTION_KEY are required to resolve a field",
        )
    path = f"/internal/fields/{field_id}"
    request_id = str(uuid.uuid4())
    headers = {
        "Accept": "application/json",
        "X-Agent-Token": token,
        "X-Service-Name": SERVICE_NAME,
        "X-Tenant-Id": tenant_id,
        "X-Request-Id": request_id,
        "X-Tenant-Assertion": create_tenant_assertion(
            key,
            SERVICE_NAME,
            tenant_id,
            key_id=os.getenv("FIELD_SERVICE_TENANT_ASSERTION_KEY_ID", "current"),
            method="GET",
            path=path,
            request_id=request_id,
        ),
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{FIELD_SERVICE_URL}{path}", headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail="field_owner_unavailable") from exc
    if resp.status_code == 404:
        raise HTTPException(404, detail=f"Field {field_id} not found")
    if resp.status_code in (401, 403):
        raise HTTPException(502, detail="field_owner_auth_contract")
    if resp.status_code != 200:
        raise HTTPException(503, detail="field_owner_unavailable")
    geometry = (resp.json() or {}).get("geometry")
    bbox = geometry_bbox(geometry) if isinstance(geometry, dict) else None
    if not bbox:
        raise HTTPException(424, detail=f"Field {field_id} has no geometry")
    return tuple(bbox)


async def fetch_sentinel_hub_token() -> str:
    """توكن Process API من هويّة CDSE (نقاط raster-service نفسها)؛ بلا اعتمادٍ ⇒ 503 صادق."""
    client_id, client_secret = _cdse_credentials()
    if not (client_id and client_secret):
        raise HTTPException(503, detail="CDSE credentials not configured")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await retry_request(
            client.post,
            SH_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
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


@app.get("/v1/mcp/tools", dependencies=[Depends(require_scope("satellite:read"))])
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
                        "tenant_id": {
                            "type": "string",
                            "description": "اختياريّ: صدىً لمستأجِر التوكن فقط؛ يُرفَض إن خالفه.",
                        },
                    },
                    "required": ["field_id"],
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
                        "tenant_id": {
                            "type": "string",
                            "description": "اختياريّ: صدىً لمستأجِر التوكن فقط؛ يُرفَض إن خالفه.",
                        },
                        "index": {"type": "string", "default": "ndvi"},
                        "since": {
                            "type": "string",
                            "format": "date",
                            "description": "YYYY-MM-DD — يقارن المشاهدات من هذا التاريخ فأحدث.",
                        },
                    },
                    "required": ["field_id"],
                },
            },
        ]
    }


@app.post("/v1/mcp/tools/call")
async def call_tool(request: Request, user: dict = Depends(require_scope("satellite:read"))):
    body = await request.json()
    tool_input = ToolInput(**body)
    cache_key = idempotency_key(user, tool_input.request_id, tool_input.name, tool_input.arguments)
    if cache_key:
        cached = IDEMPOTENCY_CACHE.get(cache_key)
        if cached and datetime.now(UTC) < cached["expires_at"]:
            return cached["result"]
    result = await _execute_tool(tool_input, user)
    if cache_key:
        IDEMPOTENCY_CACHE[cache_key] = {
            "result": result,
            "expires_at": datetime.now(UTC) + timedelta(seconds=CACHE_TTL_SECONDS),
        }
    return result


async def _execute_tool(tool_input: ToolInput, user: dict) -> dict[str, Any]:
    name = tool_input.name
    args = tool_input.arguments
    if name == "fetch_sentinel2_l2a":
        req = Sentinel2Request(**args)
        bbox = await get_field_bbox(req.field_id, _caller_tenant(user, args))
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
        bbox = await get_field_bbox(req.field_id, _caller_tenant(user, args))
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
        tenant_id = _caller_tenant(user, args)
        index = str(args.get("index") or "ndvi").strip().lower()
        date = str(args.get("date") or "latest").strip()
        if not field_id:
            raise HTTPException(422, detail="field_id is required")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await retry_request(
                client.get,
                f"{RASTER_SERVICE_URL}/v1/fields/{field_id}/indicator-grid",
                params={"index": index, "date": date, "grid": 16},
                headers=_raster_headers(tenant_id),
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
        tenant_id = _caller_tenant(user, args)
        index = str(args.get("index") or "ndvi").strip().lower()
        since = args.get("since")
        since = str(since).strip() if since else None
        if not field_id:
            raise HTTPException(422, detail="field_id is required")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await retry_request(
                client.get,
                f"{RASTER_SERVICE_URL}/v1/fields/{field_id}/timeseries",
                params={"index": index},
                headers=_raster_headers(tenant_id),
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
