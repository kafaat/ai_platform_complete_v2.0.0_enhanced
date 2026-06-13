#!/usr/bin/env python3
"""
SAHOOL Weather MCP Server
Open-Meteo + NOAA APIs with caching and idempotency
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from shared.oauth_middleware import require_scope
from shared.streamable_http import StreamableHTTPTransport

from shared.helpers import retry_request

app = FastAPI(title="SAHOOL Weather MCP Server", version="2026.1")
# ✅ OTEL
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    logging.getLogger(__name__).debug("OTEL غير مثبّت (اختياري)")
IDEMPOTENCY_CACHE: dict[str, Any] = {}
CACHE_TTL = 300

OPEN_METEO_URL = "https://api.open-meteo.com/v1"


class ForecastRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    days: int = Field(default=7, ge=1, le=16)
    hourly_vars: list[str] = Field(
        default=[
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation",
            "et0_fao_evapotranspiration",
        ]
    )


class ET0Request(BaseModel):
    lat: float
    lon: float
    date: str  # YYYY-MM-DD
    t_max: float
    t_min: float
    solar_radiation: float  # MJ/m²/day
    wind_speed: float  # m/s at 2m
    altitude: float = 1000  # meters
    latitude: float | None = None  # degrees


@app.get("/mcp/v1/tools", dependencies=[Depends(require_scope("weather:read"))])
async def list_tools():
    return {
        "tools": [
            {
                "name": "get_weather_forecast",
                "description": "تنبؤ جوي لـ 1-16 يوماً باستخدام Open-Meteo",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "days": {"type": "integer", "default": 7},
                        "hourly_vars": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["lat", "lon"],
                },
            },
            {
                "name": "calculate_hargreaves_et0",
                "description": "حساب ET0 باستخدام معادلة Hargreaves-Samani (FAO-56)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "date": {"type": "string"},
                        "t_max": {"type": "number"},
                        "t_min": {"type": "number"},
                        "solar_radiation": {"type": "number"},
                        "wind_speed": {"type": "number"},
                        "altitude": {"type": "number", "default": 1000},
                        "latitude": {"type": "number"},
                    },
                    "required": [
                        "lat",
                        "lon",
                        "date",
                        "t_max",
                        "t_min",
                        "solar_radiation",
                        "wind_speed",
                    ],
                },
            },
            {
                "name": "get_historical_weather",
                "description": "بيانات جوية تاريخية لتحليل المناخ",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"},
                    },
                    "required": ["lat", "lon", "start_date", "end_date"],
                },
            },
        ]
    }


@app.post("/mcp/v1/tools/call", dependencies=[Depends(require_scope("weather:read"))])
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
    if name == "get_weather_forecast":
        req = ForecastRequest(**args)
        params = {
            "latitude": req.lat,
            "longitude": req.lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration",
            "hourly": ",".join(req.hourly_vars),
            "forecast_days": req.days,
            "timezone": "auto",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await retry_request(
                client.get, f"{OPEN_METEO_URL}/forecast", params=params, timeout=30.0
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "source": "Open-Meteo",
                            "location": {"lat": req.lat, "lon": req.lon},
                            "forecast_days": req.days,
                            "daily": data.get("daily", {}),
                            "hourly_sample": {
                                k: data.get("hourly", {}).get(k, [])[:24] for k in req.hourly_vars
                            },
                            "generated_at": datetime.now(UTC).isoformat(),
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        }

    elif name == "calculate_hargreaves_et0":
        req = ET0Request(**args)
        t_mean = (req.t_max + req.t_min) / 2
        t_range = req.t_max - req.t_min
        import math

        lat = req.latitude if req.latitude is not None else req.lat
        j_day = datetime.strptime(req.date, "%Y-%m-%d").timetuple().tm_yday
        phi = math.radians(lat)
        dr = 1 + 0.033 * math.cos(2 * math.pi * j_day / 365)
        delta = 0.409 * math.sin(2 * math.pi * j_day / 365 - 1.39)
        ws = math.acos(-math.tan(phi) * math.tan(delta))
        ra = (
            (24 * 60 / math.pi)
            * 0.082
            * dr
            * (
                ws * math.sin(phi) * math.sin(delta)
                + math.cos(phi) * math.cos(delta) * math.sin(ws)
            )
        )
        et0 = 0.0023 * (t_mean + 17.8) * math.sqrt(t_range) * ra * 0.408

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "method": "Hargreaves-Samani",
                            "et0_mm_day": round(et0, 2),
                            "t_mean_c": round(t_mean, 2),
                            "t_range_c": round(t_range, 2),
                            "ra_mj_m2_day": round(ra, 2),
                            "date": req.date,
                            "location": {
                                "lat": req.lat,
                                "lon": req.lon,
                                "altitude_m": req.altitude,
                            },
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        }

    elif name == "get_historical_weather":
        params = {
            "latitude": args["lat"],
            "longitude": args["lon"],
            "start_date": args["start_date"],
            "end_date": args["end_date"],
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await retry_request(
                client.get, f"{OPEN_METEO_URL}/archive", params=params, timeout=30.0
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "source": "Open-Meteo Historical",
                            "period": f"{args['start_date']} to {args['end_date']}",
                            "daily": data.get("daily", {}),
                            "generated_at": datetime.now(UTC).isoformat(),
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        }

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
