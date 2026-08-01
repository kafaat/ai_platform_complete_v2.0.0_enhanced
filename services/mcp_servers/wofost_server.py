#!/usr/bin/env python3
"""
SAHOOL WOFOST MCP Server
Crop simulation via WOFOST-RUE with MCP interface
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from shared.oauth_middleware import require_scope
from shared.streamable_http import StreamableHTTPTransport

app = FastAPI(title="SAHOOL WOFOST MCP Server", version="2026.1")
# ✅ OTEL
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    logging.getLogger(__name__).debug("OTEL غير مثبّت (اختياري)")
IDEMPOTENCY_CACHE: dict[str, Any] = {}
CACHE_TTL = 300


class WOFOSTRequest(BaseModel):
    crop: str = Field(default="wheat", pattern="^(wheat|barley|maize|sorghum|millet|rice|potato)$")
    planting_date: str  # YYYY-MM-DD
    soil_type: str = Field(default="medium", pattern="^(light|medium|heavy)$")
    weather_data: list[dict] | None = None
    latitude: float = 15.0
    longitude: float = 45.0
    co2_ppm: float = 420.0
    irrigation: bool = True


class WOFOSTResult(BaseModel):
    yield_kg_ha: float
    biomass_kg_ha: float
    total_water_mm: float
    harvest_date: str
    phenology: dict[str, str]
    gdd_total: float
    stress_days: int


@app.get("/v1/mcp/tools", dependencies=[Depends(require_scope("crop:read"))])
async def list_tools():
    return {
        "tools": [
            {
                "name": "run_wofost_simulation",
                "description": "شغّل محاكاة WOFOST-RUE للمحصول مع بيانات جوية",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "crop": {
                            "type": "string",
                            "enum": [
                                "wheat",
                                "barley",
                                "maize",
                                "sorghum",
                                "millet",
                                "rice",
                                "potato",
                            ],
                        },
                        "planting_date": {"type": "string", "format": "date"},
                        "soil_type": {
                            "type": "string",
                            "enum": ["light", "medium", "heavy"],
                            "default": "medium",
                        },
                        "weather_data": {"type": "array", "items": {"type": "object"}},
                        "latitude": {"type": "number", "default": 15.0},
                        "longitude": {"type": "number", "default": 45.0},
                        "co2_ppm": {"type": "number", "default": 420.0},
                        "irrigation": {"type": "boolean", "default": True},
                    },
                    "required": ["crop", "planting_date"],
                },
            },
            {
                "name": "get_crop_parameters",
                "description": "احصل على معاملات WOFOST للمحصول المحدد",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "crop": {
                            "type": "string",
                            "enum": [
                                "wheat",
                                "barley",
                                "maize",
                                "sorghum",
                                "millet",
                                "rice",
                                "potato",
                            ],
                        }
                    },
                    "required": ["crop"],
                },
            },
        ]
    }


@app.post("/v1/mcp/tools/call", dependencies=[Depends(require_scope("crop:read"))])
async def call_tool(request: dict):
    name = request.get("name")
    args = request.get("arguments", {})
    req_id = request.get("request_id")

    if req_id and req_id in IDEMPOTENCY_CACHE:
        cached = IDEMPOTENCY_CACHE[req_id]
        if datetime.now(UTC) < cached["expires"]:
            return cached["result"]

    result = await _execute(name, args)

    if req_id:
        IDEMPOTENCY_CACHE[req_id] = {
            "result": result,
            "expires": datetime.now(UTC) + timedelta(seconds=CACHE_TTL),
        }

    return result


async def _execute(name: str, args: dict) -> dict:
    if name == "run_wofost_simulation":
        # نتحقّق من صحّة المدخل أوّلاً (422 على المُدخل السيّئ)…
        WOFOSTRequest(**args)
        # …ثمّ نرفض بأمانة: لا محرّك WOFOST-RUE حقيقيّ هنا.
        # كان _simulate_wofost يُرجِع تقديراً بثوابت مكتوبة (avg_solar=20، et0=5،
        # kc=0.8، stress=10% ثابتة) ويتجاهل weather_data المُمرَّر، ثمّ يُوسَم
        # "model":"WOFOST-RUE" — تقديمٌ لتقريبٍ على أنّه مُخرَج نموذج عمليّاتيّ.
        # أمانةً نردّ 501 حتّى يُدمَج محرّك حقيقيّ (مثل PCSE/WOFOST) بدل الاختلاق.
        raise HTTPException(
            status_code=501,
            detail=(
                "محاكاة WOFOST-RUE غير مُنفَّذة بمحرّك حقيقيّ على هذا الخادم — "
                "معطّلة بأمانة بدل إرجاع تقديرٍ بثوابت مُوسَّمٍ كمُخرَج نموذج."
            ),
        )

    elif name == "get_crop_parameters":
        crop = args["crop"]
        params = {
            "wheat": {
                "tsum1": 200,
                "tsum2": 600,
                "tdwi": 50,
                "rgrlai": 0.012,
                "span": 30,
                "wlv": 0.5,
            },
            "barley": {
                "tsum1": 180,
                "tsum2": 550,
                "tdwi": 45,
                "rgrlai": 0.014,
                "span": 28,
                "wlv": 0.45,
            },
            "maize": {
                "tsum1": 300,
                "tsum2": 800,
                "tdwi": 70,
                "rgrlai": 0.010,
                "span": 35,
                "wlv": 0.6,
            },
            "sorghum": {
                "tsum1": 250,
                "tsum2": 700,
                "tdwi": 60,
                "rgrlai": 0.011,
                "span": 32,
                "wlv": 0.55,
            },
            "millet": {
                "tsum1": 220,
                "tsum2": 650,
                "tdwi": 40,
                "rgrlai": 0.013,
                "span": 25,
                "wlv": 0.4,
            },
            "rice": {
                "tsum1": 350,
                "tsum2": 900,
                "tdwi": 80,
                "rgrlai": 0.009,
                "span": 40,
                "wlv": 0.7,
            },
            "potato": {
                "tsum1": 150,
                "tsum2": 400,
                "tdwi": 100,
                "rgrlai": 0.015,
                "span": 20,
                "wlv": 0.8,
            },
        }

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "crop": crop,
                            "parameters": params.get(crop, {}),
                            "source": "WOFOST Parameter Library SAHOOL v9",
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        }

    else:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {name}")


def _simulate_wofost(req: WOFOSTRequest) -> WOFOSTResult:
    crop_params = {
        "wheat": {"tsum1": 200, "tsum2": 600, "hi": 0.45, "rue": 3.0, "max_lai": 6.0},
        "barley": {"tsum1": 180, "tsum2": 550, "hi": 0.42, "rue": 2.8, "max_lai": 5.5},
        "maize": {"tsum1": 300, "tsum2": 800, "hi": 0.50, "rue": 3.5, "max_lai": 7.0},
        "sorghum": {"tsum1": 250, "tsum2": 700, "hi": 0.48, "rue": 3.2, "max_lai": 6.5},
        "millet": {"tsum1": 220, "tsum2": 650, "hi": 0.35, "rue": 2.5, "max_lai": 4.0},
        "rice": {"tsum1": 350, "tsum2": 900, "hi": 0.52, "rue": 3.8, "max_lai": 8.0},
        "potato": {"tsum1": 150, "tsum2": 400, "hi": 0.75, "rue": 2.0, "max_lai": 5.0},
    }

    cp = crop_params.get(req.crop, crop_params["wheat"])
    soil_factor = {"light": 0.85, "medium": 1.0, "heavy": 0.95}[req.soil_type]
    planting = datetime.strptime(req.planting_date, "%Y-%m-%d")
    gdd_total = cp["tsum1"] + cp["tsum2"]
    season_days = int((cp["tsum1"] + cp["tsum2"]) / 15)
    harvest = planting + timedelta(days=season_days)
    avg_solar_mj = 20
    total_intercepted_rad = avg_solar_mj * season_days * 0.5
    biomass = total_intercepted_rad * cp["rue"] * soil_factor * 10
    yield_kg_ha = biomass * cp["hi"]
    et0_daily = 5.0
    kc_avg = 0.8
    total_water = et0_daily * kc_avg * season_days
    if req.irrigation:
        total_water *= 0.7
    stress_days = int(season_days * 0.1)

    return WOFOSTResult(
        yield_kg_ha=round(yield_kg_ha, 2),
        biomass_kg_ha=round(biomass, 2),
        total_water_mm=round(total_water, 2),
        harvest_date=harvest.strftime("%Y-%m-%d"),
        phenology={
            "emergence": (planting + timedelta(days=int(cp["tsum1"] / 15))).strftime("%Y-%m-%d"),
            "anthesis": (
                planting + timedelta(days=int((cp["tsum1"] + cp["tsum2"] * 0.5) / 15))
            ).strftime("%Y-%m-%d"),
            "maturity": harvest.strftime("%Y-%m-%d"),
        },
        gdd_total=round(gdd_total, 2),
        stress_days=stress_days,
    )


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


if __name__ == "__main__":
    _signal.signal(_signal.SIGTERM, _handle_sigterm)
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
