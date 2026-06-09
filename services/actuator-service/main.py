#!/usr/bin/env python3
"""
SAHOOL v9.1 — Actuator Service (IoT Actuation Layer)
Scene Linkage: automation_rules → MQTT commands → device actuation
Supports: valves, pumps, fans, lights, motors via FastBee MQTT Broker
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import asyncpg
import jwt as _jwt
from aiomqtt import Client as MQTTClient
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

try:
    from shared.logging_config import setup_logging

    logger = setup_logging("actuator-service")
except ImportError:
    logging.basicConfig(
        level=logging.INFO, format='{"time":"%(asctime)s","svc":"actuator","msg":"%(message)s"}'
    )
    logger = logging.getLogger("actuator-service")

# ── Config ────────────────────────────────────────────────────
MQTT_BROKER_URL = os.getenv("MQTT_BROKER_URL", "mqtt://sahool-fastbee:1883")
DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")
_JWT_PUBLIC = os.getenv("JWT_PUBLIC_KEY", "")
JWT_SECRET = _JWT_PUBLIC if _JWT_PUBLIC else os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "RS256" if _JWT_PUBLIC else "HS256"

_pool: asyncpg.Pool | None = None


# ══════════════════════════════════════════════════════════════
# مصادقة (أمان السلامة الفيزيائيّة): التحكّم بالأجهزة يتطلّب توكناً صالحاً
# والهويّة تُشتقّ من التوكن المُتحقَّق لا من جسم الطلب.
# ══════════════════════════════════════════════════════════════
def _verify_token(authorization: str | None = Header(None)) -> dict:
    # افشل بأمان: لا سرّ → لا تشغيل (HS256 بمفتاح فارغ يقبل تزويراً)
    if not JWT_SECRET or len(JWT_SECRET) < 32:
        raise HTTPException(503, "JWT_SECRET غير مضبوط — التحكّم بالأجهزة معطّل بأمان")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "توكن مطلوب للتحكّم بالأجهزة")
    token = authorization.split(" ", 1)[1]
    try:
        payload = _jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception as e:
        raise HTTPException(401, "توكن غير صالح") from e
    if not payload.get("sub") or not payload.get("tenant_id"):
        raise HTTPException(401, "توكن ناقص الحقول الأساسيّة")
    return payload


# ══════════════════════════════════════════════════════════════
# MQTT Command Publisher
# ══════════════════════════════════════════════════════════════
async def send_mqtt_command(device_id: str, command: str, payload: dict):
    topic = f"sahool/actuator/{device_id}/command"
    ts = datetime.now(UTC).isoformat()
    # A1: وقّع الأمر بـHMAC-SHA256 ليتحقّق منه الـfirmware قبل تحريك الصمّام
    # (يطابق verifyCmdHmac في esp32_mesh_gateway.ino: HMAC(secret, cmd+"|"+ts)).
    import hashlib as _hashlib
    import hmac as _hmac

    secret = os.getenv("CMD_HMAC_SECRET", "")
    sig = ""
    if secret:
        sig = _hmac.new(secret.encode(), f"{command}|{ts}".encode(), _hashlib.sha256).hexdigest()
    message = json.dumps(
        {
            "cmd": command,
            "payload": payload,
            "ts": ts,
            "sig": sig,
        }
    )
    try:
        async with MQTTClient(MQTT_BROKER_URL) as client:
            await client.publish(topic, message, qos=1)
            logger.info(f"MQTT → {device_id}: {command}")
            return True
    except Exception as e:
        logger.error(f"MQTT failed for {device_id}: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# Scene Linkage Engine
# ══════════════════════════════════════════════════════════════
async def evaluate_rules(sensor_type: str, value: float, tenant_id: str, field_id: str):
    """Evaluate automation_rules and trigger actuators."""
    if not _pool:
        return

    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT rule_id, trigger_operator, trigger_threshold,
                       trigger_duration_sec, action_device, action_command,
                       action_payload, max_daily_runs, cooldown_sec,
                       last_triggered, today_run_count, last_reset_date,
                       time_window_start, time_window_end, days_of_week
                FROM automation_rules
                WHERE enabled = true
                  AND tenant_id = $1::uuid
                  AND trigger_sensor = $2
                """,
                tenant_id,
                sensor_type,
            )

        now = datetime.now(UTC)
        triggered = []

        for row in rows:
            # Check day of week
            if now.weekday() not in (row["days_of_week"] or list(range(7))):
                continue

            # Check time window
            if row["time_window_start"] and row["time_window_end"]:
                t = now.time()
                if not (row["time_window_start"] <= t <= row["time_window_end"]):
                    continue

            # Check daily runs
            last_reset = row["last_reset_date"]
            run_count = row["today_run_count"] or 0
            if last_reset and last_reset < now.date():
                run_count = 0
            if run_count >= (row["max_daily_runs"] or 999):
                continue

            # Check cooldown
            last_trig = row["last_triggered"]
            if last_trig and (now - last_trig).total_seconds() < (row["cooldown_sec"] or 0):
                continue

            # Evaluate condition
            op = row["trigger_operator"]
            thresh = float(row["trigger_threshold"])
            matched = False
            if op == ">" and value > thresh:
                matched = True
            elif op == ">=" and value >= thresh:
                matched = True
            elif op == "<" and value < thresh:
                matched = True
            elif op == "<=" and value <= thresh:
                matched = True
            elif op == "==" and abs(value - thresh) < 0.001:
                matched = True

            if matched:
                device = row["action_device"]
                cmd = row["action_command"]
                payload = row["action_payload"] or {}
                success = await send_mqtt_command(device, cmd, payload)

                # Log command
                await log_command(
                    rule_id=str(row["rule_id"]),
                    device_id=device,
                    command=cmd,
                    payload=payload,
                    status="sent" if success else "failed",
                    tenant_id=tenant_id,
                )

                # Update rule counters
                if _pool:
                    async with _pool.acquire() as conn:
                        await conn.execute(
                            """UPDATE automation_rules
                                SET last_triggered = NOW(),
                                    today_run_count = CASE
                                        WHEN last_reset_date = CURRENT_DATE THEN today_run_count + 1
                                        ELSE 1 END,
                                    last_reset_date = CURRENT_DATE
                                WHERE rule_id = $1""",
                            row["rule_id"],
                        )

                triggered.append(
                    {
                        "rule_id": str(row["rule_id"]),
                        "device": device,
                        "command": cmd,
                        "sent": success,
                    }
                )

        return triggered

    except Exception as e:
        logger.error(f"evaluate_rules error: {e}")
        return []


async def log_command(
    rule_id: str | None, device_id: str, command: str, payload: dict, status: str, tenant_id: str
):
    if not _pool:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO device_commands_log
                    (tenant_id, rule_id, device_id, command, payload, status, mqtt_topic, triggered_by)
                    VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8)""",
                tenant_id,
                rule_id if rule_id else None,
                device_id,
                command,
                json.dumps(payload),
                status,
                f"sahool/actuator/{device_id}/command",
                "rule",
            )
    except Exception as e:
        logger.warning(f"log_command failed: {e}")


# ══════════════════════════════════════════════════════════════
# MQTT Sensor Listener (background task)
# ══════════════════════════════════════════════════════════════
async def mqtt_sensor_listener():
    """Listen to sensor telemetry and evaluate rules."""
    topic = "sahool/+/+/telemetry/+"  # tenant/field/telemetry/sensor_type
    while True:
        try:
            async with MQTTClient(MQTT_BROKER_URL) as client:
                async with client.messages() as messages:
                    await client.subscribe(topic, qos=1)
                    logger.info(f"MQTT listener subscribed: {topic}")
                    async for message in messages:
                        try:
                            payload = json.loads(message.payload.decode())
                            parts = message.topic.value.split("/")
                            if len(parts) >= 5:
                                tenant_id = parts[1]
                                field_id = parts[2]
                                sensor_type = parts[4]
                                value = float(payload.get("value", 0))
                                await evaluate_rules(sensor_type, value, tenant_id, field_id)
                        except Exception as e:
                            logger.warning(f"Message processing error: {e}")
        except Exception as e:
            logger.error(f"MQTT listener crashed: {e}")
            await asyncio.sleep(10)


# ══════════════════════════════════════════════════════════════
# Lifespan
# ══════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    if DATABASE_URL:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        logger.info("✅ DB connected")
    else:
        logger.warning("DATABASE_URL not set — command logging disabled")

    # Start background MQTT listener (احتفظ بالمرجع لمنع GC المبكّر)
    app.state.mqtt_task = asyncio.create_task(mqtt_sensor_listener())
    logger.info("🔧 Actuator Service ready — Scene Linkage active")
    yield
    if _pool:
        await _pool.close()


app = FastAPI(title="SAHOOL Actuator Service", version="9.1.0", lifespan=lifespan)
# ✅ OTEL
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    logger.debug("OTEL غير مثبّت — التتبّع معطّل (اختياري)")


# ══════════════════════════════════════════════════════════════
# API Endpoints
# ══════════════════════════════════════════════════════════════
class CommandRequest(BaseModel):
    device_id: str
    command: str
    payload: dict = Field(default_factory=dict)
    tenant_id: str = "default"
    user_id: int | None = None
    source: str = "api"  # api|manual|schedule


@app.post("/command")
async def send_command(req: CommandRequest, claims: dict = Depends(_verify_token)):
    # الأمان: tenant_id يُشتقّ من التوكن المُتحقَّق، لا من جسم الطلب (منع انتحال).
    tenant_id = str(claims["tenant_id"])
    user_id = claims.get("sub")
    success = await send_mqtt_command(req.device_id, req.command, req.payload)
    await log_command(
        rule_id=None,
        device_id=req.device_id,
        command=req.command,
        payload=req.payload,
        status="sent" if success else "failed",
        tenant_id=tenant_id,
    )
    return {
        "device_id": req.device_id,
        "command": req.command,
        "sent": success,
        "tenant_id": tenant_id,
        "issued_by": user_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.get("/commands")
async def list_commands(limit: int = 50, claims: dict = Depends(_verify_token)):
    # الأمان: tenant_id من التوكن المُتحقَّق لا من المعامل (منع قراءة سجلّ مستأجر آخر)
    tenant_id = str(claims["tenant_id"])
    if not _pool:
        return {"commands": []}
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT log_id, device_id, command, status, sent_at, triggered_by
               FROM device_commands_log
               WHERE tenant_id = $1::uuid
               ORDER BY sent_at DESC LIMIT $2""",
            tenant_id,
            limit,
        )
    return {"commands": [dict(r) for r in rows]}


@app.get("/healthz")
@app.get("/health")
async def health():
    return {"status": "alive", "service": "actuator", "mqtt": MQTT_BROKER_URL}


@app.get("/readyz")
async def readyz():
    return {"status": "ready", "version": "9.1.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
