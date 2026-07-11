#!/usr/bin/env python3
"""
SAHOOL Weather MCP Server
Open-Meteo + NOAA APIs with caching and idempotency
"""

import json
import logging
import os
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

# محرّك الطقس الكنسيّ (services/weather-service) — مصدر ET0 المرجعيّ الوحيد.
_DEFAULT_WEATHER_SERVICE_URL = "http://sahool-weather-service:8000"


def _weather_service_url() -> str:
    return os.getenv("WEATHER_SERVICE_URL", _DEFAULT_WEATHER_SERVICE_URL).rstrip("/")


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
    # حدود تمنع math domain error (acos خارج [-1,1] عند خطوط عرض قطبيّة) و500
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    date: str  # YYYY-MM-DD
    t_max: float = Field(ge=-90, le=60)
    t_min: float = Field(ge=-90, le=60)
    solar_radiation: float = Field(ge=0)  # MJ/m²/day
    wind_speed: float = Field(ge=0)  # m/s at 2m
    altitude: float = Field(default=1000, ge=-500, le=9000)  # meters
    latitude: float | None = Field(default=None, ge=-90, le=90)  # degrees


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

        # ── WS-C.1b Zero-Legacy: لا نواة ET0 محلّيّة في هذا الخادم ──────────────
        # كان هنا تنفيذ Hargreaves-Samani سطريّ (نسخة ثانية من الصيغة خارج المحرّك).
        # الآن نستهلك **منتج ET0 المرجعيّ من محرّك الطقس** (services/weather-service:
        # POST /v1/weather/agro/et0) — المحرّك مصدر ET0 الوحيد للمنصّة. حرارة فقط ⇒
        # المحرّك يتدرّج إلى Hargreaves داخليّاً. تعذّر المحرّك ⇒ 503 fail-closed
        # (لا حساب ET0 محلّيّ بديل). t_mean/t_range حسابٌ حسابيّ بسيط (ليس نواة ET0).
        # ────────────────────────────────────────────────────────────────────
        # حارس: t_min>t_max ⇒ مدخل غير صالح. نرفض بـ400 (قبل استدعاء المحرّك).
        if req.t_min > req.t_max:
            raise HTTPException(status_code=400, detail="t_min يجب ألّا يتجاوز t_max")
        lat = req.latitude if req.latitude is not None else req.lat
        j_day = datetime.strptime(req.date, "%Y-%m-%d").timetuple().tm_yday
        body = {
            "t_max_c": req.t_max,
            "t_min_c": req.t_min,
            "lat_deg": lat,
            "elevation_m": req.altitude,
            "day_of_year": j_day,
            "valid_time": req.date,
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(f"{_weather_service_url()}/v1/weather/agro/et0", json=body)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"weather-engine ET0 unavailable — fail-closed (no local ET0): {exc}",
            ) from exc
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=503,
                detail="weather-engine ET0 unavailable — fail-closed (no local ET0)",
            )
        product = resp.json()
        et0 = product.get("et0_mm")
        if et0 is None:
            raise HTTPException(
                status_code=503,
                detail="weather-engine returned no ET0 — fail-closed (no local ET0)",
            )
        t_mean = (req.t_max + req.t_min) / 2
        t_range = req.t_max - req.t_min
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "method": product.get("method", "weather-engine"),
                            "et0_mm_day": round(float(et0), 2),
                            "t_mean_c": round(t_mean, 2),
                            "t_range_c": round(t_range, 2),
                            "quality_status": product.get("quality_status"),
                            "formula_version": product.get("formula_version"),
                            "source": "weather-engine",
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
