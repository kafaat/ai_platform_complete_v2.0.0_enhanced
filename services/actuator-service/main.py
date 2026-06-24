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

from shared.actuator_idempotency import (
    decide_fire,
    idempotency_counters,
    resolve_idempotency_mode,
)
from shared.actuator_mode import resolve_actuator_mode

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
# وضع المُشغِّل (PR #394 ⇒ fail-safe): real | simulation | disabled.
# **آمن افتراضيّاً (سلامة فيزيائيّة):** إن لم يُضبط ACTUATOR_MODE صراحةً ⇒ **simulation**
# (لا استنتاج real من MQTT_BROKER_URL — وجود وسيط ليس موافقة تشغيل). real يتطلّب opt-in
# صريحاً. simulation لا ينشر لكن يُبقي السلسلة (command → ledger → simulated_ack) حيّةً.
ACTUATOR_MODE = resolve_actuator_mode(os.getenv("ACTUATOR_MODE"), MQTT_BROKER_URL)
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

# وضع إزالة التكرار (الإغلاق المرن، PR #393): local (افتراضيّ — داخل العمليّة، السلوك الحاليّ)
# | shadow (يستشير المخزن العنقوديّ ويرصد التباين، لكنّ المحلّيّ يقرّر) | cluster (العنقوديّ
# يحسم cluster-safe، fail-soft للمحلّيّ عند تعذّره). يُغلق فجوة dict المحلّيّ per-replica دون كسر.
ACTUATOR_IDEMPOTENCY_MODE = resolve_idempotency_mode(os.getenv("ACTUATOR_IDEMPOTENCY_MODE"))
# مقاييس المراقبة (Observe قبل Enforce): عدّ القرارات حسب المفتاح (local/cluster_skip/divergence…).
_IDEM_METRICS: dict[str, int] = {}

# ── جسر القرار→التنفيذ (Shard 3، PR dispatch-bridge) ──────────────────────────
# علم تفعيل default-OFF: مُستهلِك dispatch_decisions[queued] يُطلق الأمر الفيزيائيّ عبر MQTT.
# OFF (افتراضيّ) ⇒ الجسر لا يُقلَع، ومسار الإخطار البشريّ في المنصّة يبقى المستهلك الوحيد
# («البشر أوّلاً، المضخّات آخراً»). حراسة مزدوجة: حتّى مع العلم ON، النشر الفيزيائيّ الحقيقيّ
# يتطلّب ACTUATOR_MODE=real أيضاً — وإلّا simulation/disabled ⇒ لا حركة فيزيائيّة.
FEATURE_DISPATCH_ACTUATOR = os.getenv("FEATURE_DISPATCH_ACTUATOR")
# قائمة المخاطر المسموح بأتمتتها (CSV، افتراضيّ low,medium): HIGH/CRITICAL لا تُؤتمت أبداً —
# تبقى لقرار الإنسان حتّى لو وصلت queued (سلامة فيزيائيّة).
DISPATCH_ACTUATOR_RISK_ALLOWLIST = os.getenv("DISPATCH_ACTUATOR_RISK_ALLOWLIST", "low,medium")
DISPATCH_POLL_INTERVAL_SEC = float(os.getenv("DISPATCH_POLL_INTERVAL_SEC", "5"))

# ── حراسة المسارات الفيزيائيّة per-path (Actuator Safety Hardening) ────────────
# أعلام default-OFF تمنع وصول كلّ مسار إلى send_mqtt_command أصلاً (دفاع بالعمق فوق
# ACTUATOR_MODE — نقطة الاختناق الفيزيائيّة). آمن افتراضيّاً: لا تنفيذ بلا تفعيل صريح.
#   • automation_rules (مسار المستشعرات) ⇒ FEATURE_AUTOMATION_RULES_ACTUATION
#   • POST /command (تحكّم يدويّ)        ⇒ FEATURE_MANUAL_ACTUATOR_COMMANDS
#   • جسر القرار (dispatch)              ⇒ FEATURE_DISPATCH_ACTUATOR (أعلاه)
FEATURE_AUTOMATION_RULES_ACTUATION = os.getenv("FEATURE_AUTOMATION_RULES_ACTUATION")
FEATURE_MANUAL_ACTUATOR_COMMANDS = os.getenv("FEATURE_MANUAL_ACTUATOR_COMMANDS")

# ذاكرة إزالة التكرار داخل العمليّة: مفتاح الأمر → آخر زمن إطلاق (time.monotonic).
# ملاحظة صدق: هذا حارس داخل العمليّة (per-replica) لا على مستوى العنقود؛ مع عدّة نُسَخ قد
# يُطلَق الأمر مرّةً لكلّ نسخة. لذا يُكمَّل بمخزن عنقوديّ دائم (actuator_command_dedup، v81)
# تحت ACTUATOR_IDEMPOTENCY_MODE — هذا الـdict يبقى مساراً محلّيّاً/احتياطيّاً (fail-soft).
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


async def send_mqtt_command(device_id: str, command: str, payload: dict):
    # وضع المُشغِّل (الإغلاق المرن): يتفرّع السلوك حسب ACTUATOR_MODE مع حفظ التوقيع/المستدعين.
    if ACTUATOR_MODE == "disabled":
        # لا عمليّة — السلوك الحاليّ عند غياب الوسيط (يُعيد False).
        logger.debug(f"المُشغِّل معطّل (disabled) — تخطّي الأمر إلى {device_id}: {command}")
        return False
    if ACTUATOR_MODE == "simulation":
        # محاكاة صريحة: لا نشر MQTT. نُعيد نجاحاً موسوماً (simulated=true) ونُسجّل log
        # كي تبقى السلسلة كاملة (command → ledger → simulated_ack) دون وسيط حقيقيّ.
        # صدق: هذا أثرٌ محاكى لا تنفيذ فيزيائيّ — لا تحرّك الصمّام/المضخّة فعليّاً.
        logger.info(
            f"SIMULATION → {device_id}: {command} (simulated=true، لا نشر MQTT، لا تنفيذ فيزيائيّ)"
        )
        return True
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


def _cluster_dedup_key(tenant_id: str, field_id: str, device: str, cmd: str) -> str:
    """المفتاح الفعّال للمخزن العنقوديّ (نصّ): tenant:field:device:command."""
    return f"{tenant_id}:{field_id}:{device}:{cmd}"


async def _cluster_should_fire(
    tenant_id: str, field_id: str, device: str, cmd: str, window_sec: float
) -> tuple[bool, bool]:
    """فحص-وتثبيت ذرّيّ عنقوديّ عبر القاعدة (cluster-safe) ⇒ (يُطلَق؟، المخزن متاح؟).

    INSERT … ON CONFLICT … DO UPDATE … WHERE last_fired_at < now()-window RETURNING:
    صفّ عائد ⇒ امتلكنا فتحة الإطلاق (جديد أو مرّت النافذة) ⇒ يُطلَق. لا صفّ ⇒ مكرّر ضمن
    النافذة عبر **كلّ** النُّسَخ ⇒ تخطٍّ (يمنع التنفيذ المزدوج). يضبط app.current_tenant
    قبل الاستعلام (RLS). **fail-soft**: تعذّر القاعدة ⇒ (False, available=False) ليتولّى
    decide_fire الرجوع المحلّيّ — لا نوقف الفعل الميدانيّ كلّيّاً لعطل قاعدة.
    """
    if not _pool:
        return False, False
    key = _cluster_dedup_key(tenant_id, field_id, device, cmd)
    try:
        async with _pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)", str(tenant_id)
                )
                got = await conn.fetchval(
                    """INSERT INTO actuator_command_dedup (dedup_key, tenant_id, last_fired_at)
                       VALUES ($1, $2::uuid, now())
                       ON CONFLICT (dedup_key) DO UPDATE SET last_fired_at = now()
                         WHERE actuator_command_dedup.last_fired_at
                               < now() - make_interval(secs => $3)
                       RETURNING dedup_key""",
                    key,
                    str(tenant_id),
                    float(window_sec),
                )
        return (got is not None), True
    except Exception as e:  # noqa: BLE001 — fail-soft: عطل المخزن لا يوقف الفعل (رجوع محلّيّ)
        logger.warning("مخزن idempotency العنقوديّ غير متاح (رجوع محلّيّ): %s", e)
        return False, False


async def _cluster_clear(tenant_id: str, field_id: str, device: str, cmd: str) -> None:
    """يحذف مفتاح المخزن العنقوديّ (فشل الأمر ⇒ لا تمنع النافذة إعادة محاولة مشروعة). best-effort."""
    if not _pool:
        return
    key = _cluster_dedup_key(tenant_id, field_id, device, cmd)
    try:
        async with _pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, true)", str(tenant_id)
                )
                await conn.execute("DELETE FROM actuator_command_dedup WHERE dedup_key = $1", key)
    except Exception as e:  # noqa: BLE001 — best-effort: فشل التنظيف لا يكسر مسار الفشل/التعويض
        logger.warning("تعذّر مسح مفتاح idempotency العنقوديّ: %s", e)


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
    # حراسة per-path (Safety Hardening): أتمتة القواعد معطّلة افتراضيّاً ⇒ لا تقييم ولا
    # إطلاق ولا تغيير حالة. تفعيل فيزيائيّ فعليّ يتطلّب أيضاً ACTUATOR_MODE=real (مزدوج).
    if not _automation_actuation_enabled(FEATURE_AUTOMATION_RULES_ACTUATION):
        logger.debug("أتمتة القواعد معطّلة (FEATURE_AUTOMATION_RULES_ACTUATION) — تخطّي")
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
                # الإغلاق المرن: المحلّيّ يُحسَب دائماً (يبقى دافئاً للرجوع)؛ العنقوديّ حسب الوضع.
                local_fire = _dedup_should_fire(
                    dedup_key, time.monotonic(), ACTUATOR_DEDUP_WINDOW_SEC, _dedup_last_fired
                )
                if ACTUATOR_IDEMPOTENCY_MODE == "local":
                    fire = local_fire
                    cluster_fire, cluster_ok = False, False
                else:
                    cluster_fire, cluster_ok = await _cluster_should_fire(
                        tenant_id, field_id, device, cmd, ACTUATOR_DEDUP_WINDOW_SEC
                    )
                    fire, _ = decide_fire(
                        ACTUATOR_IDEMPOTENCY_MODE, local_fire, cluster_fire, cluster_ok
                    )
                    # شرط القبول 4: تعذّر المخزن في cluster ⇒ سجّل صراحةً (رجوع محلّيّ، لا crash).
                    if ACTUATOR_IDEMPOTENCY_MODE == "cluster" and not cluster_ok:
                        logger.warning(
                            "cluster_idempotency_unavailable=true — رجوع محلّيّ مؤقّت "
                            f"(حقل {field_id}، جهاز {device})"
                        )
                # المقاييس المعتمدة (الأسماء الموحّدة) — تُرصَد قبل الفرض (shadow_divergence=0 معيار الانتقال).
                for _name in idempotency_counters(
                    ACTUATOR_IDEMPOTENCY_MODE, local_fire, cluster_fire, cluster_ok, fire
                ):
                    _IDEM_METRICS[_name] = _IDEM_METRICS.get(_name, 0) + 1
                if not fire:
                    logger.info(
                        f"إزالة تكرار ({ACTUATOR_IDEMPOTENCY_MODE}): تخطّي أمر مكرّر '{cmd}' على "
                        f"{device} (نافذة {ACTUATOR_DEDUP_WINDOW_SEC:.0f}ث، حقل {field_id})"
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
                    if ACTUATOR_IDEMPOTENCY_MODE != "local":
                        await _cluster_clear(tenant_id, field_id, device, cmd)
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
    rule_id: str | None,
    device_id: str,
    command: str,
    payload: dict,
    status: str,
    tenant_id: str,
    triggered_by: str = "rule",
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
                triggered_by,
            )
    except Exception as e:
        logger.warning(f"log_command failed: {e}")


# ══════════════════════════════════════════════════════════════
# جسر القرار→التنفيذ (Shard 3): مُستهلِك dispatch_decisions[queued]
# ──────────────────────────────────────────────────────────────
# يُغلِق الحلقة من قرار المنصّة إلى الأمر الفيزيائيّ — لكن محروساً مزدوجاً ومحاكاةً-أوّلاً.
# صدق صريح: send_mqtt_command ينشر بلا ack ⇒ exec_status='executed' يعني «الأمر نُشِر
# للوسيط» لا «الصمّام/المضخّة تحرّكت فعليّاً». التنفيذ الفيزيائيّ الحقيقيّ يتطلّب
# ACTUATOR_MODE=real (وإلّا simulation: أثرٌ محاكى، لا حركة). القرار يصل queued فقط بعد
# اجتياز حواجز المنصّة وجمع الموافقات (state=READY) — الجسر يستهلك المُخلَّص لا يتجاوز الحواجز.
_DISPATCH_TRUTHY = {"1", "true", "yes", "on"}


def _dispatch_consumer_enabled(env_value: str | None) -> bool:
    """دالّة نقيّة: العلم default-OFF (غياب/قيمة مجهولة ⇒ معطّل، fail-closed)."""
    return (env_value or "").strip().lower() in _DISPATCH_TRUTHY


def _automation_actuation_enabled(env_value: str | None) -> bool:
    """دالّة نقيّة: علم أتمتة القواعد (مسار المستشعرات)، default-OFF fail-closed."""
    return (env_value or "").strip().lower() in _DISPATCH_TRUTHY


def _manual_commands_enabled(env_value: str | None) -> bool:
    """دالّة نقيّة: علم التحكّم اليدويّ POST /command، default-OFF fail-closed."""
    return (env_value or "").strip().lower() in _DISPATCH_TRUTHY


def _safety_status(mode: str, dispatch_on: bool, automation_on: bool, manual_on: bool) -> dict:
    """دالّة نقيّة: تكوين سلامة طبقة التنفيذ الفيزيائيّ — **لا أسرار** (لا broker/tokens/
    tenant/secrets)، حالة فقط. physical_execution_enabled = (الوضع real)."""
    real = mode == "real"
    status = {
        "actuator_mode": mode,
        "physical_execution_enabled": real,
        "dispatch_bridge_enabled": bool(dispatch_on),
        "automation_rules_enabled": bool(automation_on),
        "manual_command_enabled": bool(manual_on),
    }
    if real:
        status["warning"] = "⚠️ PHYSICAL ACTUATION ENABLED — REAL MQTT COMMANDS MAY BE SENT ⚠️"
    return status


def _parse_risk_allowlist(env_value: str | None) -> set[str]:
    """دالّة نقيّة: قائمة المخاطر المسموح بأتمتتها (CSV) ⇒ مجموعة محارف صغيرة. فارغ ⇒ low,medium."""
    if not env_value or not env_value.strip():
        return {"low", "medium"}
    return {p.strip().lower() for p in env_value.split(",") if p.strip()}


def _is_risk_allowed(risk_level, allowlist: set[str]) -> bool:
    """دالّة نقيّة: هل يُسمح بأتمتة هذا المستوى؟ HIGH/CRITICAL خارج الافتراضيّ ⇒ لا (تبقى للإنسان)."""
    return str(risk_level or "").strip().lower() in allowlist


def _parse_dispatch_command(command):
    """دالّة نقيّة fail-safe: يفكّ حمولة أمر القرار ⇒ ``(device_id, cmd, payload)`` أو ``None``.

    أمر فاسد/ناقص ⇒ ``None`` (لا رمي) ⇒ يُعامَل القرار كـfailed (لا تخمين، لا إطلاق أعمى).
    يتسامح مع المفاتيح: ``device_id``/``device`` و``command``/``cmd``.
    """
    if isinstance(command, str):
        try:
            command = json.loads(command)
        except (ValueError, TypeError):
            return None
    if not isinstance(command, dict):
        return None
    device_id = command.get("device_id") or command.get("device")
    cmd = command.get("command") or command.get("cmd")
    if not isinstance(device_id, str) or not device_id:
        return None
    if not isinstance(cmd, str) or not cmd:
        return None
    payload = command.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    return device_id, cmd, payload


def _dispatch_outcome_status(send_success: bool) -> str:
    """دالّة نقيّة: نتيجة النشر ⇒ حالة التنفيذ. نجاح النشر ⇒ executed (نُشِر≠نُفِّذ)، وإلّا failed."""
    return "executed" if send_success else "failed"


async def _claim_queued_decisions(conn, allowlist: set[str], batch_size: int):
    """يطالب ذرّيّاً queued→dispatched (FOR UPDATE SKIP LOCKED) ⇒ لا إطلاق مزدوج.

    المطالبة الذرّيّة (``UPDATE … WHERE exec_status='queued'``) تضمن أنّ صفّاً لا يُلتقَط
    مرّتين (ولا من نُسَخ actuator متعدّدة): بعد المطالبة لم يعد 'queued'. HIGH/CRITICAL
    مستبعَدة عبر allowlist، وrisk_level=NULL مستبعَد (lower(NULL) لا يطابق) — يبقيان للإنسان.
    """
    return await conn.fetch(
        """
        UPDATE dispatch_decisions SET exec_status = 'dispatched'
        WHERE decision_id IN (
            SELECT decision_id FROM dispatch_decisions
            WHERE exec_status = 'queued' AND lower(risk_level) = ANY($1::text[])
            ORDER BY created_at ASC
            LIMIT $2
            FOR UPDATE SKIP LOCKED
        )
        RETURNING decision_id, tenant_id::text AS tenant_id, field_id,
                  recommendation_id, action_type, risk_level, command
        """,
        list(allowlist),
        batch_size,
    )


async def _device_belongs_to_tenant(conn, device_id: str, tenant_id: str) -> bool:
    """حارس عزل فيزيائيّ: هل الجهاز يخصّ مستأجِر القرار؟ (fail-closed: غير موجود/خطأ ⇒ False).

    نظير ``_authorize_device_control`` لكن مقابل مستأجِر القرار لا توكن. يضمن **عدم نشر أمر
    فيزيائيّ عابر للمستأجرين** مهما كان مصدر صفّ الطابور: تحت RLS صارم (سياق غير مضبوط) يعود
    NULL ⇒ False ⇒ لا نشر (آمن)؛ ومع وصول الخدمة يتحقّق الربط بالمستأجِر صراحةً.
    """
    try:
        owner = await conn.fetchval(
            "SELECT tenant_id::text FROM iot_devices WHERE device_id = $1", device_id
        )
    except Exception as e:  # noqa: BLE001 — تعذّر التحقّق ⇒ fail-closed (لا نشر أعمى)
        logger.warning("جسر القرار: تعذّر التحقّق من ملكيّة الجهاز %s: %s", device_id, e)
        return False
    return owner is not None and owner == tenant_id


async def _dispatch_one(conn, row) -> str:
    """ينشر أمر قرار مُطالَب به (dispatched) ⇒ يُنهيه executed/failed + يُسجّل. يُرجِع الحالة."""
    decision_id = row["decision_id"]
    parsed = _parse_dispatch_command(row["command"])
    if parsed is None:
        # أمر فاسد/غائب ⇒ failed (لا إطلاق أعمى، صدق).
        await conn.execute(
            "UPDATE dispatch_decisions SET exec_status = 'failed' "
            "WHERE decision_id = $1 AND exec_status = 'dispatched'",
            decision_id,
        )
        logger.warning("جسر القرار: أمر فاسد/غائب للقرار %s ⇒ failed", decision_id)
        return "failed"
    device_id, cmd, payload = parsed

    # حارس السلامة الفيزيائيّة + العزل: لا يُنشَر أمر إلّا لجهاز يخصّ مستأجِر القرار
    # (نظير _authorize_device_control في /command). يمنع تحكّماً فيزيائيّاً عابراً للمستأجرين
    # مهما كان مصدر الصفّ، ويُفشِل بأمان تحت RLS صارم. الفشل ⇒ failed بلا نشر.
    if not await _device_belongs_to_tenant(conn, device_id, row["tenant_id"]):
        await conn.execute(
            "UPDATE dispatch_decisions SET exec_status = 'failed' "
            "WHERE decision_id = $1 AND exec_status = 'dispatched'",
            decision_id,
        )
        logger.warning(
            "جسر القرار: الجهاز %s لا يخصّ مستأجِر القرار %s ⇒ failed (لا نشر فيزيائيّ)",
            device_id,
            decision_id,
        )
        await log_command(
            rule_id=None,
            device_id=device_id,
            command=cmd,
            payload={"decision_id": decision_id},
            status=f"dispatch_denied_{ACTUATOR_MODE}",
            tenant_id=row["tenant_id"],
            triggered_by="dispatch",
        )
        return "failed"
    # أثرِ الحمولة بمرجع القرار (تتبّع) دون تغيير الأمر الأصليّ.
    enriched = {
        **payload,
        "decision_id": decision_id,
        "field_id": row["field_id"],
        "recommendation_id": row["recommendation_id"],
    }
    try:
        success = await send_mqtt_command(device_id, cmd, enriched)
    except Exception as e:  # noqa: BLE001 — أيّ تعذّر نشر ⇒ failed (لا رمي يكسر الحلقة)
        logger.error("جسر القرار: تعذّر نشر أمر القرار %s: %s", decision_id, e)
        success = False
    status = _dispatch_outcome_status(bool(success))
    await conn.execute(
        "UPDATE dispatch_decisions SET exec_status = $2 "
        "WHERE decision_id = $1 AND exec_status = 'dispatched'",
        decision_id,
        status,
    )
    # تدقيق: سجّل في device_commands_log مع mode (sim/real) + النتيجة — صدق «نُشِر≠نُفِّذ».
    await log_command(
        rule_id=None,
        device_id=device_id,
        command=cmd,
        payload=enriched,
        status=f"dispatch_{status}_{ACTUATOR_MODE}",
        tenant_id=row["tenant_id"],
        triggered_by="dispatch",
    )
    return status


async def dispatch_consumer_loop():
    """عامل خلفيّ (نظير mqtt_sensor_listener): يستهلك dispatch_decisions[queued] محاكاةً-أوّلاً.

    محروس مزدوجاً: لا يُقلَع إلّا بـ``FEATURE_DISPATCH_ACTUATOR=on``؛ والنشر الفيزيائيّ الحقيقيّ
    يتطلّب ``ACTUATOR_MODE=real`` (وإلّا simulation ⇒ أثرٌ محاكى). best-effort: أيّ خطأ دفعة
    يُسجَّل ولا يكسر الحلقة (تدهور رشيق). يقرأ الطابور كخدمة (نظير evaluate_rules: بلا سياق
    مستأجِر مفرد) — الوصول يخضع لدور الـactuator (إن حجبه RLS في بيئة غير مُهيّأة ⇒ لا شيء
    يُستهلَك، وهو آمن مع التعطيل الافتراضيّ).
    """
    if not _dispatch_consumer_enabled(FEATURE_DISPATCH_ACTUATOR):
        return
    if not _pool:
        logger.warning("جسر القرار: FEATURE_DISPATCH_ACTUATOR=on لكن لا DATABASE_URL — معطّل")
        return
    allowlist = _parse_risk_allowlist(DISPATCH_ACTUATOR_RISK_ALLOWLIST)
    logger.info(
        "🔗 جسر القرار→التنفيذ مُفعَّل (mode=%s، allowlist=%s) — صدق: نُشِر≠نُفِّذ؛ "
        "النشر الفيزيائيّ الحقيقيّ يتطلّب ACTUATOR_MODE=real",
        ACTUATOR_MODE,
        sorted(allowlist),
    )
    while True:
        try:
            async with _pool.acquire() as conn:
                rows = await _claim_queued_decisions(conn, allowlist, batch_size=20)
                for row in rows:
                    await _dispatch_one(conn, row)
        except asyncio.CancelledError:
            break
        except Exception as e:  # noqa: BLE001 — خطأ دفعة ⇒ سجّل واستمرّ (لا كسر)
            logger.error("جسر القرار: خطأ دفعة: %s", e)
        await asyncio.sleep(DISPATCH_POLL_INTERVAL_SEC)


# ══════════════════════════════════════════════════════════════
# MQTT Sensor Listener (background task)
# ══════════════════════════════════════════════════════════════
async def mqtt_sensor_listener():
    """Listen to sensor telemetry and evaluate rules."""
    # المستمع يتطلّب وسيطاً حقيقيّاً للاشتراك — يعمل في وضع real فقط. في simulation/
    # disabled لا وسيط (أو لا نشر) ⇒ يُعطَّل المستمع (يطابق سلوك _mqtt_disabled الحاليّ
    # عند الاستنتاج الافتراضيّ، دون تغيير سلوك real).
    if ACTUATOR_MODE != "real":
        logger.info(f"المُشغِّل في وضع {ACTUATOR_MODE} — مستمع MQTT معطّل (لا وسيط للاشتراك)")
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
    # تحذير إقلاع صاخب (Safety Hardening): التنفيذ الفيزيائيّ الحقيقيّ لا يقع إلّا بتعيين
    # ACTUATOR_MODE=real صريحاً (الافتراضيّ simulation، fail-safe). أعلِنه بوضوح عند الإقلاع.
    if ACTUATOR_MODE == "real":
        logger.warning("⚠️ PHYSICAL ACTUATION ENABLED — REAL MQTT COMMANDS MAY BE SENT ⚠️")
        logger.warning(
            "⚠️ ACTUATOR_MODE=real — راجِع /safety-status وتأكّد أنّ أعلام المسارات مقصودة ⚠️"
        )
    else:
        logger.info("المُشغِّل في وضع %s (آمن افتراضيّاً) — لا نشر فيزيائيّ حقيقيّ", ACTUATOR_MODE)
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
    # جسر القرار→التنفيذ (Shard 3، محروس بعلم default-OFF): يُقلَع فقط عند التفعيل الصريح.
    # OFF ⇒ مسار الإخطار البشريّ في المنصّة هو المستهلك (البشر أوّلاً، المضخّات آخراً).
    app.state.dispatch_task = None
    if _dispatch_consumer_enabled(FEATURE_DISPATCH_ACTUATOR):
        app.state.dispatch_task = asyncio.create_task(dispatch_consumer_loop())
    else:
        logger.info(
            "جسر القرار→التنفيذ معطّل (FEATURE_DISPATCH_ACTUATOR غير مضبوط) — "
            "مسار الإخطار البشريّ في المنصّة هو المستهلك"
        )
    logger.info("🔧 Actuator Service ready — Scene Linkage active")
    yield
    # إيقاف نظيف للجسر (نظير OutboxWorker): cancel ثمّ await ابتلاع CancelledError.
    dispatch_task = getattr(app.state, "dispatch_task", None)
    if dispatch_task is not None:
        dispatch_task.cancel()
        try:
            await dispatch_task
        except asyncio.CancelledError:
            pass
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
    # حراسة per-path (Safety Hardening): التحكّم اليدويّ معطّل افتراضيّاً ⇒ 403 صريح
    # (لا استدعاء send_mqtt_command). تفعيله يتطلّب FEATURE_MANUAL_ACTUATOR_COMMANDS.
    if not _manual_commands_enabled(FEATURE_MANUAL_ACTUATOR_COMMANDS):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "manual_actuator_commands_disabled_by_safety_policy",
                "message_ar": "التحكّم اليدويّ بالمُشغّلات معطّل بسياسة السلامة (فعّل FEATURE_MANUAL_ACTUATOR_COMMANDS)",
            },
        )
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
    # نكشف الوضع الفعّال للمراقبة (الصدق): simulation يُعلَن صراحةً فلا يُظنّ تنفيذاً حقيقيّاً.
    return {
        "status": "alive",
        "service": "actuator",
        "mqtt": MQTT_BROKER_URL,
        "mode": ACTUATOR_MODE,
    }


@app.get("/readyz")
async def readyz():
    # جاهزيّة حقيقيّة: حين تُضبط DATABASE_URL يجب أن يكون pool القاعدة حيّاً
    # (تسجيل أوامر الأجهزة يعتمد عليه). نتحقّق بـSELECT 1؛ تعذُّره ⇒ 503 لا «جاهز» كاذب.
    # حين لا DATABASE_URL مضبوطة (وضع متدرّج معلَن: تسجيل الأوامر معطّل) ⇒ جاهز بصدق.
    if _pool is not None:
        try:
            async with _pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as e:
            logger.warning(f"readyz: قاعدة البيانات غير جاهزة — {e}")
            raise HTTPException(503, {"status": "not_ready", "reason": "db"}) from e
    return {"status": "ready", "version": "9.1.0"}


@app.get("/idempotency/metrics")
async def idempotency_metrics():
    """مقاييس إزالة التكرار (المراقبة قبل الفرض): الوضع + عدّ القرارات حسب المفتاح.

    قراءة فقط — يُمكّن مرحلة Observe من نمط الإغلاق المرن: قبل ترقية الوضع إلى cluster،
    راقِب shadow_divergence (كم مرّة كان العنقوديّ سيمنع تكراراً فاتَ المحلّيّ) و
    cluster_unavailable_fallback (صحّة المخزن). لا أسرار — عدّادات مجرّدة فقط.
    """
    return {
        "mode": ACTUATOR_IDEMPOTENCY_MODE,
        "dedup_window_sec": ACTUATOR_DEDUP_WINDOW_SEC,
        "metrics": dict(_IDEM_METRICS),
        "local_store_size": len(_dedup_last_fired),
    }


@app.get("/safety-status")
async def safety_status():
    """تكوين سلامة طبقة التنفيذ الفيزيائيّ — يُعلِن الوضع وحراسة كلّ مسار صراحةً.

    **لا أسرار** (لا broker URL ولا tokens ولا tenant ids ولا أسرار أجهزة) — حالة فقط.
    آمن افتراضيّاً: بلا متغيّرات بيئة ⇒ mode=simulation وكلّ المسارات معطّلة (لا نشر فيزيائيّ).
    """
    return _safety_status(
        ACTUATOR_MODE,
        _dispatch_consumer_enabled(FEATURE_DISPATCH_ACTUATOR),
        _automation_actuation_enabled(FEATURE_AUTOMATION_RULES_ACTUATION),
        _manual_commands_enabled(FEATURE_MANUAL_ACTUATOR_COMMANDS),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
