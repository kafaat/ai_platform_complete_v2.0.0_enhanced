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
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import asyncpg
import jwt as _jwt
from aiomqtt import Client as MQTTClient
from fastapi import Depends, FastAPI, Header, HTTPException, Query
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
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ التوكن (تدقيق B: iss لم يُفحَص).
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}

# نافذة إزالة التكرار (Saga / idempotency): لا يُعاد إطلاق نفس الأمر الفعّال
# خلال هذه المدّة بالثواني. قابلة للضبط عبر البيئة، الافتراضيّ 60ث.
ACTUATOR_DEDUP_WINDOW_SEC = float(os.getenv("ACTUATOR_DEDUP_WINDOW_SEC", "60"))

# ذاكرة إزالة التكرار داخل العمليّة: مفتاح الأمر → آخر زمن إطلاق (time.monotonic).
# ملاحظة صدق: هذا حارس داخل العمليّة (per-replica) لا على مستوى العنقود؛
# مع عدّة نُسَخ قد يُطلَق الأمر مرّةً لكلّ نسخة. الـidempotency الحقيقيّ
# (exactly-once عنقوديّ) يتطلّب مخزناً مشتركاً دائماً (Redis/DB) لا dict محلّيّاً.
_dedup_last_fired: dict[tuple[str, str, str, str], float] = {}

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
        payload = _jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], audience="sahool")
    except Exception as e:
        raise HTTPException(401, "توكن غير صالح") from e
    # تدقيق B: افرض المُصدِر بعد فكّ ناجح — مُصدِر مجهول ⇒ 401 كتوكن غير صالح.
    if payload.get("iss") not in _ALLOWED_ISS:
        raise HTTPException(401, "مُصدِر التوكن غير مسموح")
    if not payload.get("sub") or not payload.get("tenant_id"):
        raise HTTPException(401, "توكن ناقص الحقول الأساسيّة")
    return payload


# أدوار التحكّم الفيزيائيّ بالأجهزة — تطابق صلاحيّة المنصّة DEVICE_MANAGE
# (owner/manager فقط؛ agronomist/worker/viewer لهم DEVICE_VIEW لا MANAGE).
# السلامة الفيزيائيّة: تشغيل صمّام/مضخّة قرار إدارة لا قراءة.
_DEVICE_CONTROL_ROLES = {"owner", "manager"}


async def _authorize_device_control(claims: dict, device_id: str) -> None:
    """يحرس التحكّم الفيزيائيّ: فحص الدور + ملكيّة الجهاز للمستأجر (fail-closed).

    أمان السلامة الفيزيائيّة + عزل المستأجرين:
      • الدور: لا يُشغّل الأجهزةَ إلّا owner/manager (مطابقة DEVICE_MANAGE) — viewer/
        worker/agronomist ⇒ 403.
      • الملكيّة: device_id يجب أن يخصّ مستأجِر التوكن (iot_devices.tenant_id) — وإلّا
        يستطيع مستأجِر A تشغيل جهاز مستأجِر B (كسر عزل + خطر فيزيائيّ). غير موجود/لمستأجِر
        آخر ⇒ 404 (لا تسريب وجود عابر للمستأجرين).
      • fail-closed: تعذّر التحقّق من القاعدة (لا pool/خطأ) ⇒ 503، لا تشغيل بلا تحقّق.
    """
    role = str(claims.get("role", "")).strip().lower()
    if role not in _DEVICE_CONTROL_ROLES:
        raise HTTPException(403, "الدور لا يملك صلاحيّة التحكّم بالأجهزة (owner/manager فقط)")

    tenant_id = str(claims["tenant_id"])
    if not _pool:
        # لا يمكن التحقّق من ملكيّة الجهاز بلا قاعدة ⇒ ارفض (لا تشغيل أعمى).
        raise HTTPException(503, "تعذّر التحقّق من ملكيّة الجهاز — التحكّم معطّل بأمان")
    try:
        async with _pool.acquire() as conn:
            owner_tenant = await conn.fetchval(
                "SELECT tenant_id::text FROM iot_devices WHERE device_id = $1", device_id
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ قاعدة ⇒ fail-closed
        raise HTTPException(503, "تعذّر التحقّق من ملكيّة الجهاز — التحكّم معطّل بأمان") from e
    # غير موجود أو لمستأجِر آخر ⇒ 404 موحّد (لا تمييز يكشف وجود أجهزة مستأجِر آخر).
    if owner_tenant is None or owner_tenant != tenant_id:
        raise HTTPException(404, "الجهاز غير موجود")


# ══════════════════════════════════════════════════════════════
# MQTT Command Publisher
# ══════════════════════════════════════════════════════════════
def _parse_mqtt_broker_url(url: str) -> tuple[str, int]:
    """يستخرج (hostname, port) من mqtt://host:port — aiomqtt.Client يحتاج المضيف
    والمنفذ لا URL كاملاً (تمرير URL كاملاً كـhostname يفشل في DNS)."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return (parsed.hostname or "localhost"), (parsed.port or 1883)


def _mqtt_disabled() -> bool:
    """MQTT معطّل إذا لم يُضبط العنوان أو بدأ بـ'disabled' — للتشغيل بلا وسيط."""
    return not MQTT_BROKER_URL or MQTT_BROKER_URL.startswith("disabled")


async def send_mqtt_command(device_id: str, command: str, payload: dict):
    if _mqtt_disabled():
        logger.debug(f"MQTT معطّل — تخطّي الأمر إلى {device_id}: {command}")
        return False
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
    host, port = _parse_mqtt_broker_url(MQTT_BROKER_URL)
    try:
        async with MQTTClient(host, port=port) as client:
            await client.publish(topic, message, qos=1)
            logger.info(f"MQTT → {device_id}: {command}")
            return True
    except Exception as e:
        logger.error(f"MQTT failed for {device_id}: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# إزالة التكرار (Idempotency) — حارس داخل العمليّة
# ══════════════════════════════════════════════════════════════
def _dedup_should_fire(
    key: tuple[str, str, str, str],
    now: float,
    window_sec: float,
    store: dict[tuple[str, str, str, str], float],
) -> bool:
    """دالّة قرار نقيّة (قابلة للاختبار بزمن مُموَّه): هل يُسمح بإطلاق هذا الأمر؟

    - `key`: (tenant_id, field_id, device_id, command) — الأمر الفعّال.
    - `now`: زمن أحاديّ الاتّجاه (time.monotonic) للمقارنة.
    - تُعيد True وتُحدّث آخر زمن إطلاق إن مرّت `window_sec` منذ آخر إطلاق
      (أو لم يُطلَق من قبل)، وإلّا False (مكرّر ضمن النافذة).
    - تُنظّف المدخلات الأقدم من النافذة في كلّ فحص لمنع نموّ الذاكرة بلا حدّ.
    """
    # تنظيف المدخلات القديمة (أقدم من النافذة) — يبقي القاموس صغيراً.
    if window_sec > 0:
        stale = [k for k, ts in store.items() if (now - ts) >= window_sec]
        for k in stale:
            del store[k]

    last = store.get(key)
    if last is not None and window_sec > 0 and (now - last) < window_sec:
        return False  # مكرّر ضمن نافذة التهدئة — تخطَّ الإطلاق
    store[key] = now
    return True


# الأوامر العكسيّة المعروفة للتعويض (Saga compensation): فتح↔إغلاق، تشغيل↔إيقاف.
# إن لم يوجد عكس واضح ⇒ تُطلَب تسوية يدويّة (لا نُخمّن).
_INVERSE_COMMANDS = {
    "open": "close",
    "close": "open",
    "on": "off",
    "off": "on",
    "start": "stop",
    "stop": "start",
}


def _inverse_command(command: str) -> str | None:
    """يُعيد الأمر العكسيّ المعروف (تعويض)، أو None إن لم يوجد عكس واضح."""
    return _INVERSE_COMMANDS.get((command or "").strip().lower())


async def _compensate(
    prior: list[dict], tenant_id: str, failed_device: str, failed_cmd: str
) -> None:
    """خطّاف تعويض أوّليّ (Saga compensation hook) — ليس آلة حالات كاملة.

    عند فشل أمر ضمن تسلسل، نحاول إرسال العكس الواضح للأوامر السابقة الناجحة
    (open↔close, on↔off, start↔stop). إن لم يوجد عكس واضح ⇒ نُسجّل أنّ
    التعويض يتطلّب تدخّلاً يدويّاً (لا نُخمّن أمراً قد يكون خطيراً فيزيائيّاً).

    حدود الصدق: هذا أوّل خطوة فقط — لا سجلّ Saga دائم، ولا إعادة محاولة،
    ولا ضمان نجاح التعويض نفسه (نُسجّل فشله إن حدث). التعويض الكامل يحتاج
    سجلّ Saga دائماً + آلة حالات + سياسة إعادة محاولة.
    """
    logger.warning(
        f"COMPENSATION: فشل الأمر '{failed_cmd}' على {failed_device} ⇒ "
        f"بدء تعويض {len(prior)} أمر/أوامر سابقة ناجحة"
    )
    # نعوّض بترتيب عكسيّ (الأحدث أوّلاً) — أقرب لإلغاء التسلسل.
    for done in reversed(prior):
        inv = _inverse_command(done["command"])
        if inv is None:
            logger.warning(
                f"COMPENSATION: لا عكس واضح للأمر '{done['command']}' على "
                f"{done['device']} ⇒ مطلوب تعويض يدويّ (manual compensation required)"
            )
            await log_command(
                rule_id=done.get("rule_id"),
                device_id=done["device"],
                command=done["command"],
                payload=done.get("payload") or {},
                status="failed",
                tenant_id=tenant_id,
            )
            continue
        logger.warning(
            f"COMPENSATION: إرسال العكس '{inv}' إلى {done['device']} (لإلغاء '{done['command']}')"
        )
        comp_ok = await send_mqtt_command(done["device"], inv, done.get("payload") or {})
        await log_command(
            rule_id=done.get("rule_id"),
            device_id=done["device"],
            command=inv,
            payload=done.get("payload") or {},
            status="sent" if comp_ok else "failed",
            tenant_id=tenant_id,
        )
        if not comp_ok:
            logger.error(
                f"COMPENSATION: فشل أمر التعويض '{inv}' على {done['device']} ⇒ مطلوب تدخّل يدويّ"
            )


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
        # أوامر هذا التقييم التي نجحت — لاستخدامها في التعويض إن فشل أمر لاحق.
        succeeded: list[dict] = []

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

                # إزالة التكرار (idempotency): تخطَّ إن أُطلق نفس الأمر الفعّال
                # (tenant, field, device, command) خلال نافذة التهدئة.
                dedup_key = (tenant_id, field_id, device, cmd)
                if not _dedup_should_fire(
                    dedup_key,
                    time.monotonic(),
                    ACTUATOR_DEDUP_WINDOW_SEC,
                    _dedup_last_fired,
                ):
                    logger.info(
                        f"إزالة تكرار: تخطّي أمر مكرّر '{cmd}' على {device} "
                        f"(نافذة {ACTUATOR_DEDUP_WINDOW_SEC:.0f}ث، حقل {field_id})"
                    )
                    triggered.append(
                        {
                            "rule_id": str(row["rule_id"]),
                            "device": device,
                            "command": cmd,
                            "sent": False,
                            "deduped": True,
                        }
                    )
                    continue

                # إرسال الأمر مع التقاط الفشل/الاستثناء لتشغيل خطّاف التعويض.
                try:
                    success = await send_mqtt_command(device, cmd, payload)
                except Exception as send_err:
                    logger.error(f"send_mqtt_command raised for {device}: {send_err}")
                    success = False

                # Log command
                await log_command(
                    rule_id=str(row["rule_id"]),
                    device_id=device,
                    command=cmd,
                    payload=payload,
                    status="sent" if success else "failed",
                    tenant_id=tenant_id,
                )

                if not success:
                    # فشل أمر ضمن التسلسل ⇒ شغّل تعويض الأوامر السابقة الناجحة.
                    # نُسقط مفتاح dedup للأمر الفاشل كي لا تمنع النافذة إعادة محاولة
                    # لاحقة مشروعة (الفشل لم يُحرّك الجهاز فعليّاً).
                    _dedup_last_fired.pop(dedup_key, None)
                    await _compensate(succeeded, tenant_id, device, cmd)
                    triggered.append(
                        {
                            "rule_id": str(row["rule_id"]),
                            "device": device,
                            "command": cmd,
                            "sent": False,
                        }
                    )
                    # أوقف التسلسل بعد الفشل والتعويض (لا نُكمل أوامر تالية).
                    return triggered

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

                entry = {
                    "rule_id": str(row["rule_id"]),
                    "device": device,
                    "command": cmd,
                    "sent": success,
                }
                triggered.append(entry)
                # سجّل النجاح (مع payload) كمرشّح للتعويض إن فشل أمر لاحق.
                succeeded.append(
                    {
                        "rule_id": str(row["rule_id"]),
                        "device": device,
                        "command": cmd,
                        "payload": payload,
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
    if _mqtt_disabled():
        logger.info("MQTT_BROKER_URL غير مضبوط — مستمع MQTT معطّل")
        return
    topic = "sahool/+/+/telemetry/+"  # tenant/field/telemetry/sensor_type
    host, port = _parse_mqtt_broker_url(MQTT_BROKER_URL)
    while True:
        try:
            async with MQTTClient(host, port=port) as client:
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
        # FINDING-001: ارفض الإقلاع إن تجاوز دور الاتّصال RLS (fail-closed افتراضيّاً).
        from shared.db_role_guard import assert_db_role_rls_safe

        await assert_db_role_rls_safe(_pool, service="actuator-service")
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
    # حارس السلامة الفيزيائيّة + العزل: فحص الدور + ملكيّة الجهاز للمستأجِر (fail-closed).
    await _authorize_device_control(claims, req.device_id)
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
async def list_commands(
    limit: int = Query(50, ge=1, le=500), claims: dict = Depends(_verify_token)
):
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
