"""
SAHOOL v9.1.0 — services/soil-service/main.py
IoT soil sensor data ingestion and analysis.
MED-SOIL-01 FIX: service implementation added.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

try:
    from shared.logging_config import setup_logging

    logger = setup_logging("soil-service")
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format='{"time":"%(asctime)s","svc":"soil","level":"%(levelname)s","msg":"%(message)s"}',
    )
    logger = logging.getLogger("soil-service")

DATABASE_URL = os.getenv("DATABASE_URL", "")
NATS_URL = os.getenv("NATS_URL", "nats://sahool-nats:4222")
# مصادقة خدمة-لخدمة: استيعاب بيانات المستشعرات يكتب للقاعدة — يتطلّب توكناً
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")


def _require_service_token(x_agent_token: str = Header(None)) -> None:
    """يمنع حقن بيانات مستشعرات مزوّرة. فشل آمن لو التوكن غير مضبوط."""
    if not AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — الاستيعاب معطّل بأمان")
    if x_agent_token != AGENT_TOKEN:
        raise HTTPException(401, "توكن خدمة غير صالح")


VERSION = "9.1.0"

_pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    if DATABASE_URL:
        # FIX: statement_cache_size معامل عميل asyncpg لا إعداد خادم — في
        # server_settings يفشل الاتصال بـ"unrecognized configuration parameter".
        _pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=5, statement_cache_size=0
        )
    logger.info("✅ soil-service started")
    yield
    if _pool:
        await _pool.close()


app = FastAPI(title="SAHOOL Soil Service", version=VERSION, lifespan=lifespan)


@app.get("/healthz")
@app.get("/health")
async def health():
    return {"status": "alive", "service": "soil-service", "version": VERSION}


@app.get("/readyz")
async def readyz():
    try:
        if _pool:
            async with _pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        return {"status": "ready"}
    except Exception as e:
        from fastapi import HTTPException

        raise HTTPException(503, str(e)) from e


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/soil/readings/{field_id}")
async def get_readings(field_id: str, limit: int = 100):
    """Get soil sensor readings for a field."""
    if not _pool:
        return {"error": "DB not connected"}
    async with _pool.acquire() as conn:
        # H5 FIX: أعمدة soil_readings الفعليّة (init_v8.sql) هي
        # temperature_c/ph/ec_ds_m/nitrogen_mg_kg/... — نُسمّيها بأسماء الـAPI
        # عبر alias. السابق كان يقرأ أعمدة غير موجودة (temperature/humidity/
        # ph_level/ec_level/n_ppm...) ⇒ UndefinedColumnError على كلّ قراءة.
        rows = await conn.fetch(
            """SELECT sensor_id,
                      temperature_c     AS temperature,
                      moisture_pct,
                      ph                AS ph_level,
                      ec_ds_m           AS ec_level,
                      nitrogen_mg_kg    AS n_ppm,
                      phosphorus_mg_kg  AS p_ppm,
                      potassium_mg_kg   AS k_ppm,
                      recorded_at
               FROM soil_readings
               WHERE field_id = $1
               ORDER BY recorded_at DESC LIMIT $2""",
            field_id,
            limit,
        )
    return [dict(r) for r in rows]


class SoilReading(BaseModel):
    """نموذج تحقّق لقراءة مستشعر التربة — يرفض البيانات المشوّهة."""

    field_id: str = Field(min_length=1, max_length=64)
    sensor_id: str = Field(min_length=1, max_length=64)
    temperature: float | None = Field(None, ge=-50, le=80)
    moisture_pct: float | None = Field(None, ge=0, le=100)
    ph_level: float | None = Field(None, ge=0, le=14)
    ec_level: float | None = Field(None, ge=0, le=50)
    # H5 FIX: NPK كان يُقرأ ولا يُكتب ولا حقل له — أُضيف ليُدخَل فعلاً.
    n_ppm: float | None = Field(None, ge=0)
    p_ppm: float | None = Field(None, ge=0)
    k_ppm: float | None = Field(None, ge=0)
    tenant_id: str = ""


@app.post("/soil/ingest")
async def ingest_reading(reading: SoilReading, x_agent_token: str = Header(None)):
    """Ingest IoT soil sensor data — يتطلّب توكن خدمة + تحقّق Pydantic."""
    _require_service_token(x_agent_token)
    if not _pool:
        return {"error": "DB not connected"}
    async with _pool.acquire() as conn:
        # H5 FIX: نكتب الأعمدة الفعليّة بما فيها NPK. tenant_id عمود UUID
        # nullable ⇒ نحوّل "" إلى NULL لتفادي فشل الإدخال.
        await conn.execute(
            """
            INSERT INTO soil_readings
            (field_id, sensor_id, temperature_c, moisture_pct,
             ph, ec_ds_m, nitrogen_mg_kg, phosphorus_mg_kg, potassium_mg_kg,
             recorded_at, tenant_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW(),$10)
            ON CONFLICT DO NOTHING
        """,
            reading.field_id,
            reading.sensor_id,
            reading.temperature,
            reading.moisture_pct,
            reading.ph_level,
            reading.ec_level,
            reading.n_ppm,
            reading.p_ppm,
            reading.k_ppm,
            (reading.tenant_id or None),
        )
    return {"status": "ingested"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
