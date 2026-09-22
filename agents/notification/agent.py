"""
SAHOOL v9.0 — agents/notification/agent.py (مُصلَح)
══════════════════════════════════════════════════
إصلاحات:
  ✅ aiosmtplib بدلاً من smtplib (كان يحظر event loop)
  ✅ asyncio.to_thread() كـ fallback لـ smtplib
  ✅ WebSocket manager محسّن مع connection cleanup
  ✅ 8 اشتراكات NATS مع durable names

Condition-gated capabilities:
  FCM HTTP v1 uses explicitly provisioned FCM_CREDENTIALS_JSON and the shared
  credential validator. Provider acceptance requires a named message receipt.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import asyncpg
import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket
from fastapi.responses import Response
from nats.aio.client import Client as NATS
from nats.js import JetStreamContext
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from shared.fcm import fcm_push_active, send_push
from shared.notification_consumers import SUBSCRIPTIONS, queue_name, validate_queue
from shared.security.access_tokens import access_token_verification_key, verify_access_token
from shared.security.trusted_tenant import service_token_ok
from shared.tracing import configure_tracing

logger = logging.getLogger("notification-agent")
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","svc":"notification-agent","msg":"%(message)s"}',
)

NATS_URL = os.getenv("NATS_URL", "nats://sahool-nats:4222")
DB_URL = os.getenv("DATABASE_URL", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASSWORD", "")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# FCM: السرّ يُقرأ وقت التشغيل في fcm_push_active()/send_push (لا ثابت استيراد).
_fcm_dormant_logged = False

# ── WebSocket manager ─────────────────────────────────────────


# ── Async email (FIXED: no blocking smtplib) ──────────────────
async def send_email_async(to: str, subject: str, html: str) -> bool:
    """Non-blocking email using aiosmtplib."""
    if not SMTP_USER or not SMTP_PASS:
        return False
    try:
        import aiosmtplib  # pip install aiosmtplib

        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASS,
            start_tls=True,
            timeout=15,
        )
        return True
    except ImportError:
        # Fallback: run blocking smtplib in thread pool (not blocking event loop)
        return await asyncio.to_thread(_send_email_blocking, to, subject, html)
    except Exception as e:
        logger.warning(f"Email failed: {e}")
        return False


def _send_email_blocking(to: str, subject: str, html: str) -> bool:
    """Fallback: runs in thread pool via asyncio.to_thread()."""
    import smtplib

    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        return True
    except Exception as e:
        logger.warning(f"Blocking email failed: {e}")
        return False


# ── TTS Voice Notification (Yemeni Arabic) ──────────────────────
async def send_tts_voice(text: str, telegram_chat_id: int, voice: str = "yemeni_male") -> bool:
    """Generate TTS voice via tts-service for high-priority alerts.

    Returns True on success, False otherwise (caller may fallback to text).
    """
    tts_url = os.getenv("TTS_URL", "http://sahool-tts-service:8000")
    tts_token = os.getenv("SAHOOL_AGENT_TOKEN", "")
    if not (tts_token and telegram_chat_id):
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{tts_url}/v1/tts/synthesize",
                json={"text": text[:1000], "voice": voice},
                # مصادقة خدمة-لخدمة: tts يتحقّق من السرّ المشترك X-Agent-Token
                # (== SAHOOL_AGENT_TOKEN)، لا من حاملة Bearer لتوكن وكيل. كان
                # Bearer هو نوع الاعتماد الخاطئ (tts يتوقّع JWT بـaud=sahool في
                # حاملة Bearer) فيُرفَض دوماً. نُرسل الاعتماد الذي يتحقّق منه tts.
                headers={"X-Agent-Token": tts_token},
            )
        if resp.status_code != 200:
            return False
        logger.info(
            f"TTS voice ready: chat={telegram_chat_id} bytes={len(resp.content)} voice={voice}"
        )
        # Forward bytes to telegram-bot service for delivery
        # (telegram-bot exposes internal /push-voice for service-to-service)
        return True
    except Exception as e:
        logger.error(f"TTS voice failed: {e}")
        return False


async def send_telegram(chat_id: str, text: str) -> bool:
    if not TG_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
            return r.status_code == 200
    except Exception as e:
        logger.warning(f"Telegram failed: {e}")
        return False


# ── FCM/APNs push (CONDITION-GATED: fcm_push capability) ───────
def _fcm_truthy(v: str) -> bool:
    """A non-empty, non-falsey env value counts as set (rejects 0/false/no/off)."""
    return v.strip().lower() not in ("", "0", "false", "no", "off")


# ── C4/M1: علم الـpush للموبايل (default OFF) + قرار الإرسال vs السجلّ الاحتياطيّ ──
# إطار «implemented-but-off-by-default»: الـpush مُنفَّذ (send_push/FCM) لكنّه opt-in
# صريح بهذا العلم. OFF (افتراضيّ) أو FCM خامل ⇒ **سجلّ احتياطيّ دائم** بدل إسقاط صامت.
_MOBILE_PUSH_FLAG = "FEATURE_MOBILE_PUSH"


def mobile_push_enabled() -> bool:
    """هل push الموبايل مُفعَّل؟ default OFF (يُقرأ وقت الاستدعاء). علم opt-in صريح
    فوق قدرة FCM — التفعيل يتطلّب العلم **و** FCM_CREDENTIALS_JSON الصالح معاً."""
    return _fcm_truthy(os.getenv(_MOBILE_PUSH_FLAG, ""))


def push_decision(*, flag_on: bool, push_enabled: bool, has_token: bool, fcm_active: bool) -> str:
    """يقرّر إجراء الـpush — دالّة نقيّة مُختبَرة. يُرجِع:

    - ``"skip"``        لا رغبة (push مُعطَّل لدى المستخدم أو لا token) ⇒ لا شيء.
    - ``"send"``        رغبة + العلم on + FCM نشط ⇒ إرسال push فعليّ.
    - ``"record_only"`` رغبة لكن (العلم off أو FCM خامل) ⇒ سجلّ احتياطيّ دائم
                        (create_notification_record) — **لا إسقاط صامت** (صدق).
    """
    if not (push_enabled and has_token):
        return "skip"
    if flag_on and fcm_active:
        return "send"
    return "record_only"


# ── DB helpers ────────────────────────────────────────────────
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool | None:
    global _pool
    if not _pool and DB_URL:
        try:
            # statement_cache_size معامل عميل asyncpg (لا server_settings): وضعه في
            # server_settings يجعل asyncpg يرسل «SET statement_cache_size» للخادم فيفشل
            # الاتّصال ⇒ /readyz يعيد 503. =0 يعطّل ذاكرة العبارات المُحضّرة (توافق pgbouncer).
            _pool = await asyncpg.create_pool(
                DB_URL, min_size=1, max_size=5, statement_cache_size=0
            )
        except Exception as e:
            logger.warning(f"DB connection failed: {e}")
    return _pool


class InvalidNotification(ValueError):
    """An event cannot be routed safely; retain it in the dead-letter subject."""


class DeliveryUnavailable(RuntimeError):
    """Keep the JetStream message owed when persistence or delivery fails."""


@asynccontextmanager
async def _tenant_connection(tenant_id: str, user_id: str = ""):
    pool = await get_pool()
    if pool is None:
        raise DeliveryUnavailable("notification_database_unavailable")
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true), "
            "set_config('app.current_user_id', $2, true)",
            str(tenant_id),
            str(user_id),
        )
        yield conn


async def get_prefs(user_id: str, tenant_id: str) -> dict | None:
    """تفضيلات المستخدم بالهويّة التي تكتبها المنصّة: ``(tenant_id, user_ref)`` نصّاً.

    كانت تُحوِّل الموضوع إلى ``int`` وتقرأ عمود ``user_id`` القديم (INTEGER، FK إلى
    ``users.id``) بينما ``PUT /api/v1/notifications/preferences`` يكتب الصفّ تحت
    ``user_ref`` النصّيّ (v38). فكلّ تفضيلٍ محفوظٍ عبر الـAPI الحاليّ كان يُفوَّت، وموضوعٌ
    UUID كان يسقط قبل الاستعلام أصلاً (Copilot على #997).
    """
    user_ref = str(user_id)
    async with _tenant_connection(tenant_id, user_ref) as conn:
        row = await conn.fetchrow(
            "SELECT * FROM notification_preferences WHERE tenant_id=$1::uuid AND user_ref=$2",
            tenant_id,
            user_ref,
        )
        return dict(row) if row else None


def _delivery_key(data: dict) -> str:
    identity = data.get("_delivery_id") or data.get("event_id") or data.get("alert_key")
    if not identity:
        identity = hashlib.sha256(
            json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
    return f"notification:{identity}:user:{data.get('user_id', '')}"


async def _deliver_channel(data: dict, channel: str, send=None, reason: str | None = None) -> None:
    """Use existing tenant-scoped receipts to skip already successful channels.

    The database row lock serializes redeliveries. Provider acceptance followed
    by a crash before commit can still repeat a send: this is at-least-once, not
    a claim of exactly-once delivery at external providers.
    """
    tenant = data.get("tenant_id")
    if not tenant:
        raise InvalidNotification("notification_tenant_required")
    key = _delivery_key(data)
    failed = False
    async with _tenant_connection(str(tenant), str(data.get("user_id", ""))) as conn:
        await conn.execute(
            "INSERT INTO notification_delivery (tenant_id, alert_key, channel, status, error) "
            "VALUES ($1::uuid, $2, $3, 'queued', $4) "
            "ON CONFLICT (tenant_id, alert_key, channel) DO NOTHING",
            str(tenant),
            key,
            channel,
            reason,
        )
        status = await conn.fetchval(
            "SELECT status FROM notification_delivery "
            "WHERE tenant_id=$1::uuid AND alert_key=$2 AND channel=$3 FOR UPDATE",
            str(tenant),
            key,
            channel,
        )
        if status is None:
            raise DeliveryUnavailable("notification_receipt_unavailable")
        if status in {"sent", "delivered"} or send is None:
            return
        try:
            sent = await send()
        except Exception:
            sent = False
        failed = not sent
        await conn.execute(
            "UPDATE notification_delivery SET status=$4, error=$5, updated_at=now() "
            "WHERE tenant_id=$1::uuid AND alert_key=$2 AND channel=$3",
            str(tenant),
            key,
            channel,
            "sent" if sent else "failed",
            None if sent else "provider_delivery_failed",
        )
    if failed:
        raise DeliveryUnavailable(f"{channel}_delivery_failed")


async def _record_push_fallback(data: dict, reason: str) -> None:
    await _deliver_channel(data, "push", reason=reason)


# ── Event dispatcher ──────────────────────────────────────────
EVENT_EMOJI = {
    "satellite": "🛰️",
    "weather_alert": "🌩️",
    "pest_alert": "🐛",
    "irrigation_rec": "💧",
    "fertilizer_rec": "🌱",
    "low_stock": "📦",
    "task_assigned": "✅",
    "economic_analysis": "💰",
    "guardrails_block": "🛑",
}


def make_html(title: str, message: str, data: dict) -> str:
    rows = "".join(
        f"<tr><td style='color:#666'>{k}</td><td><b>{v}</b></td></tr>" for k, v in data.items()
    )
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial;direction:rtl;padding:20px">
<h2 style="color:#16a34a">{title}</h2><p>{message}</p>
{"<table border='0'>" + rows + "</table>" if rows else ""}
<hr><p style="color:#9ca3af;font-size:12px">إشعار آلي — SAHOOL v9.0</p>
</body></html>"""


async def dispatch(data: dict):
    et = data.get("event_type", "")
    user_id = data.get("user_id")
    title = data.get("title", f"{EVENT_EMOJI.get(et, '📢')} {et}")
    message = data.get("message", "")
    extra = data.get("data", {})

    tenant_id = data.get("tenant_id")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise InvalidNotification("notification_tenant_required")
    if user_id:
        await manager.send_to_user(str(user_id), data)
    else:
        await manager.broadcast_tenant(tenant_id, data)

    if not user_id:
        return

    prefs = await get_prefs(str(user_id), tenant_id)
    if not prefs:
        return

    event_types = prefs.get("event_types", [])
    if isinstance(event_types, str):
        event_types = json.loads(event_types)
    if et not in event_types:
        return

    html = make_html(title, message, extra)

    # كلُّ قناةٍ محاولةٌ مستقلّة (C01، التقرير الجنائيّ الموحَّد ٢): كان فشلُ البريد يرفع
    # `DeliveryUnavailable` فيغادر التوزيعُ قبل بلوغ Telegram وPush، ثمّ يُعاد الحدثُ كلُّه
    # حتّى ينتهي في dead-letter دون أن تُجرَّب القنواتُ السليمة قطّ. الآن تُجرَّب كلُّها،
    # وتُجمَع الفاشلةُ ويُرفَع بعد آخرها فتُعاد الرسالةُ من JetStream — والإيصالاتُ
    # الناجحة (`sent`) تُتخطّى في المحاولة التالية داخل `_deliver_channel` فلا تتكرّر.
    planned: list[tuple[str, Callable[[], Awaitable[None]]]] = []

    if prefs.get("email_enabled") and prefs.get("email_address"):
        planned.append(
            (
                "email",
                lambda: _deliver_channel(
                    data,
                    "email",
                    lambda: send_email_async(prefs["email_address"], f"[سهول] {title}", html),
                ),
            )
        )

    if prefs.get("telegram_enabled") and prefs.get("telegram_chat_id"):
        text = f"<b>{title}</b>\n{message}"
        if extra:
            text += "\n" + "\n".join(f"• {k}: {v}" for k, v in extra.items())
        planned.append(
            (
                "telegram",
                lambda: _deliver_channel(
                    data, "telegram", lambda: send_telegram(str(prefs["telegram_chat_id"]), text)
                ),
            )
        )

    # Mobile push (C4/M1) — خلف علم FEATURE_MOBILE_PUSH (default off) + سجلّ احتياطيّ:
    # send عند (العلم on ∧ FCM نشط)؛ record_only عند رغبة المستخدم بلا تفعيل ⇒ سجلّ
    # دائم بدل إسقاط صامت؛ skip عند عدم الرغبة. لا تغيير لباقي القنوات.
    decision = push_decision(
        flag_on=mobile_push_enabled(),
        push_enabled=bool(prefs.get("push_enabled")),
        has_token=bool(prefs.get("push_token")),
        fcm_active=fcm_push_active(),
    )
    if decision == "send":
        planned.append(
            (
                "push",
                lambda: _deliver_channel(
                    data, "push", lambda: send_push(str(prefs["push_token"]), title, message)
                ),
            )
        )
    elif decision == "record_only":
        planned.append(
            (
                "push",
                lambda: _record_push_fallback(data, reason="mobile_push_disabled_or_fcm_dormant"),
            )
        )

    failed: list[str] = []
    for channel, attempt in planned:
        try:
            await attempt()
        except DeliveryUnavailable as exc:
            logger.warning("Channel retained for retry: %s (%s)", channel, exc)
            failed.append(channel)
    if failed:
        raise DeliveryUnavailable("channels_failed:" + ",".join(failed))


# ── NATS subscriptions ────────────────────────────────────────
_nc: NATS | None = None
_js: JetStreamContext | None = None

CONSUMER_MODE = os.getenv("NOTIFICATION_CONSUMER_MODE", "legacy")


_subscriptions: dict = {}


async def _dead_letter(msg, reason: str) -> None:
    if _js is None:
        raise DeliveryUnavailable("dead_letter_unavailable")
    metadata = msg.metadata
    identity = f"{metadata.stream}:{metadata.sequence.stream}"
    await _js.publish(
        "sahool.notification.dead_letter",
        json.dumps(
            {
                "source_subject": msg.subject,
                "source_id": identity,
                "reason": reason,
                "payload": msg.data.decode("utf-8", errors="replace"),
            }
        ).encode(),
        headers={"Nats-Msg-Id": f"notification-dead-letter:{identity}"},
    )
    await msg.term()


async def handle_msg(msg):
    try:
        data = json.loads(msg.data.decode())
        if not isinstance(data, dict):
            raise InvalidNotification("notification_object_required")
        metadata = msg.metadata
        data["_delivery_id"] = f"{metadata.stream}:{metadata.sequence.stream}"
        await dispatch(data)
    except (InvalidNotification, UnicodeError, json.JSONDecodeError) as exc:
        try:
            await _dead_letter(msg, type(exc).__name__)
        except Exception:
            await msg.nak(delay=30)
    except Exception as exc:
        logger.warning("Notification retry: %s", type(exc).__name__)
        try:
            if msg.metadata.num_delivered >= 10:
                await _dead_letter(msg, "delivery_attempts_exhausted")
            else:
                await msg.nak(delay=30)
        except Exception:
            await msg.nak(delay=30)
    else:
        await msg.ack()


async def _ensure_subscriptions():
    from nats.js.api import ConsumerConfig, StreamConfig
    from nats.js.errors import NotFoundError

    if CONSUMER_MODE not in {"legacy", "queue_v1"}:
        raise ValueError("invalid_notification_consumer_mode")
    try:
        await _js.stream_info("sahool")
    except NotFoundError:
        if CONSUMER_MODE == "queue_v1":
            raise  # Provisioning is an explicit operator step, never a startup reset.
        await _js.add_stream(StreamConfig(name="sahool", subjects=["sahool.>"]))
    for subject, durable in SUBSCRIPTIONS:
        if durable in _subscriptions:
            continue
        try:
            if CONSUMER_MODE == "queue_v1":
                info = await _js.consumer_info("sahool", queue_name(durable))
                validate_queue(info.config, subject, durable)
                _subscriptions[durable] = await _js.subscribe_bind(
                    stream="sahool",
                    consumer=queue_name(durable),
                    config=info.config,
                    cb=handle_msg,
                    manual_ack=True,
                )
                continue
            _subscriptions[durable] = await _js.subscribe(
                subject,
                cb=handle_msg,
                durable=durable,
                manual_ack=True,
                config=ConsumerConfig(ack_wait=120, max_deliver=-1),
            )
        except Exception as exc:
            logger.warning("Subscription unavailable: %s (%s)", durable, type(exc).__name__)


async def _subscription_loop():
    while True:
        try:
            await _ensure_subscriptions()
        except Exception as exc:
            logger.warning("Subscription initialization retry: %s", type(exc).__name__)
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _nc, _js, _pool
    access_token_verification_key()
    _subscriptions.clear()
    _nc = NATS()
    await _nc.connect(NATS_URL)
    _js = _nc.jetstream()
    task = asyncio.create_task(_subscription_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await _nc.close()
        _subscriptions.clear()
        if _pool:
            await _pool.close()
            _pool = None


# ── FastAPI app ───────────────────────────────────────────────
app = FastAPI(title="SAHOOL Notification Agent", version="9.1.0", lifespan=lifespan)

configure_tracing(app, "sahool-notification-agent")


# ── WebSocket Connection Manager (secured) ─────────────────────
class ConnectionManager:
    def __init__(self, max_per_user: int = 5):
        self.connections: dict[str, set] = defaultdict(set)
        # عزل المستأجِر: نتتبّع مستأجِر كلّ مستخدم متّصل كي نوجّه أحداث المستأجِر
        # (التى تحمل tenant_id لا user_id) لمستخدمي ذلك المستأجِر فقط — لا بثّ عابر
        # للمستأجرين (كان broadcast يصل كلّ المستخدمين عبر كلّ المستأجرين = تسريب).
        self._user_tenant: dict[str, str] = {}
        self._max_per_user = max_per_user
        self._lock = asyncio.Lock()

    @property
    def total_connections(self) -> int:
        """إجماليّ اتّصالات WebSocket الحيّة عبر كلّ المستخدمين (لـ/health)."""
        return sum(len(s) for s in self.connections.values())

    async def connect(self, user_id: str, websocket, tenant_id: str = "") -> bool:
        async with self._lock:
            if not tenant_id or self._user_tenant.get(user_id, tenant_id) != tenant_id:
                return False
            if len(self.connections[user_id]) >= self._max_per_user:
                return False
            self.connections[user_id].add(websocket)
            if tenant_id:
                self._user_tenant[user_id] = tenant_id
            return True

    async def disconnect(self, user_id: str, websocket):
        async with self._lock:
            self.connections[user_id].discard(websocket)
            if not self.connections[user_id]:
                del self.connections[user_id]
                self._user_tenant.pop(user_id, None)

    async def send_to_user(self, user_id: str, data: dict):
        if not data.get("tenant_id") or self._user_tenant.get(user_id) != str(data["tenant_id"]):
            return
        dead = set()
        for ws in list(self.connections.get(user_id, [])):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            await self.disconnect(user_id, ws)

    async def broadcast_tenant(self, tenant_id: str, data: dict):
        """يبثّ لمستخدمي مستأجِر واحد فقط (عزل المستأجِر). إن خلا المستأجِر من
        مستخدمين متّصلين فهو لا-عمل آمن (لا تسرّب لمستأجرين آخرين)."""
        if not tenant_id:
            return
        for uid in list(self.connections):
            if self._user_tenant.get(uid) == tenant_id:
                await self.send_to_user(uid, data)

    async def broadcast(self, data: dict):
        for uid in list(self.connections):
            await self.send_to_user(uid, data)


manager = ConnectionManager(max_per_user=5)


# ── WebSocket JWT Validation ─────────────────────────────────────
def _validate_ws_token(token: str) -> dict:
    return verify_access_token(token)


async def _ws_receive_loop(websocket, verified_user_id: str):
    """حلقة الاستقبال المشتركة بين المسارين (التوكن في الـquery أو في الرسالة
    الأولى) لتفادي أيّ تباعد في السلوك. تحافظ على W04: مهلة 60ث على الاستقبال."""
    try:
        while True:
            try:
                # W04: 60s timeout on receive
                data = await asyncio.wait_for(websocket.receive_json(), timeout=60.0)
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except TimeoutError:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break
    finally:
        await manager.disconnect(verified_user_id, websocket)
        logger.info(f"WS disconnected: user={verified_user_id}")


@app.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket):
    """Secure WebSocket with JWT auth, connection limit, timeout.

    مصادقة بإطار-أوّل حصراً (auth-frame): لم نعُد نقرأ التوكن من الـquery
    (?token=…) إطلاقاً — كان يتسرّب إلى سجلّات الوكلاء/الخوادم (access logs)
    والوسطاء. العميل يتّصل أوّلاً ثمّ يُرسل إطاراً أوّل {"type":"auth","token":"…"}
    ونتحقّق منه قبل تقديم أيّ أحداث. غياب الإطار/بطلانه ⇒ إغلاق (fail-closed).
    """
    # لا بدّ من قبول الاتصال قبل أن نستطيع استقبال إطار المصادقة (المتصفّح لا
    # يملك وسيلة للتحقّق قبل القبول دون تمرير التوكن في الـquery).
    await websocket.accept()
    try:
        # ننتظر إطار المصادقة بمهلة قصيرة كي لا يبقى اتصال مجهول مفتوحاً طويلاً.
        auth_frame = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
    except Exception:
        await websocket.close(code=1008, reason="Auth handshake timeout")
        return

    auth_frame = auth_frame if isinstance(auth_frame, dict) else {}
    ws_token = auth_frame.get("token", "")
    if auth_frame.get("type") != "auth" or not ws_token:
        await websocket.close(code=1008, reason="Missing auth frame")
        return

    # W01: Full JWT validation (بعد القبول، لكن قبل تقديم أيّ أحداث — نُبقي على
    # خاصيّة "تحقّق قبل خدمة الأحداث").
    try:
        payload = _validate_ws_token(ws_token)
        verified_user_id = payload["sub"]
        tenant_id = payload.get("tenant_id", "")
    except ValueError as e:
        await websocket.close(code=1008, reason=str(e))
        return

    # W03: Ignore client-supplied user_id — use JWT sub
    # W09: Max connections per user. نمرّر tenant_id (من مطالبة JWT) لعزل المستأجِر.
    if not await manager.connect(verified_user_id, websocket, tenant_id):
        await websocket.close(code=1008, reason="Max connections reached")
        return

    logger.info(f"WS connected: user={verified_user_id} tenant={tenant_id}")
    await _ws_receive_loop(websocket, verified_user_id)


def _require_agent_token(x_agent_token: str = Header(None, alias="X-Agent-Token")) -> None:
    """يحمي نقاط الاختبار (تُرسِل إشعارات/تنشر NATS) بالتوكن الخدميّ — fail-closed.

    كانت بلا مصادقة ⇒ انتحال إشعارات + حقن أحداث NATS عشوائيّة في الناقل الداخليّ.
    """
    expected = os.getenv("SAHOOL_AGENT_TOKEN", "")
    # ``service_token_ok`` يقارن ثابتَ الزمن ويردّ False على سرٍّ فارغ — فيُغني عن
    # ``not expected`` وعن ``!=`` معاً، ولا يُغيّر الرمز (403 هنا بخلاف 401/503 في
    # الخدمات: هذه نقطةُ اختبارٍ لا قناةُ استيعاب).
    if not service_token_ok(x_agent_token, expected):
        raise HTTPException(403, "نقطة اختبار محميّة بـSAHOOL_AGENT_TOKEN")


@app.post("/notifications/test")
async def test_notification(payload: dict, _: None = Depends(_require_agent_token)):
    test_event = {
        "event_type": "satellite",
        "user_id": payload.get("user_id"),
        "title": "🧪 إشعار تجريبي — SAHOOL v9",
        "message": "هذا اختبار لنظام الإشعارات",
        "data": {"test": True},
        "tenant_id": payload.get("tenant_id"),
    }
    await dispatch(test_event)
    return {"status": "sent"}


@app.get("/health")
@app.get("/healthz")
async def health():
    return {"status": "ok", "ws_connections": manager.total_connections}


@app.get("/readyz")
async def readyz():
    if CONSUMER_MODE not in {"legacy", "queue_v1"}:
        raise HTTPException(503, {"status": "not_ready", "reason": "consumer_mode"})
    if _nc is None or not _nc.is_connected or _js is None:
        raise HTTPException(503, {"status": "not_ready", "reason": "nats"})
    missing = []
    for subject, durable in SUBSCRIPTIONS:
        try:
            if durable not in _subscriptions:
                raise RuntimeError("subscription_missing")
            name = queue_name(durable) if CONSUMER_MODE == "queue_v1" else durable
            info = await _js.consumer_info("sahool", name)
            if CONSUMER_MODE == "queue_v1":
                validate_queue(info.config, subject, durable)
                if not info.push_bound:
                    raise RuntimeError("queue_subscription_unbound")
            elif info.config.filter_subject != subject:
                raise RuntimeError("subscription_filter_mismatch")
        except Exception:
            sub = _subscriptions.pop(durable, None)
            if sub is not None:
                with suppress(Exception):
                    await sub.unsubscribe()
            missing.append(durable)
    if missing:
        raise HTTPException(
            503, {"status": "not_ready", "reason": "subscriptions", "missing": missing}
        )
    if not DB_URL:
        raise HTTPException(503, {"status": "not_ready", "reason": "database_not_configured"})
    if DB_URL:
        try:
            pool = await get_pool()
            # get_pool يبتلع فشل الاتّصال ويُعيد None — مع DB_URL مضبوطة، pool=None
            # يعني القاعدة متعذّرة فعلاً ⇒ غير جاهز (لا جاهز كاذب).
            if pool is None:
                raise RuntimeError("db pool unavailable")
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as e:
            raise HTTPException(503, {"status": "not_ready", "reason": "db"}) from e
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    """مقاييس Prometheus — يلتقطها prometheus/grafana في المنظومة."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8123)


# ══ Test publisher for NATS topics (development) ══
@app.post("/notification/test")
async def send_test_notification(
    tenant_id: str, event_type: str, data: dict, _: None = Depends(_require_agent_token)
):
    """Test endpoint to publish NATS events for testing notification subscriptions."""
    from shared.helpers import publish_event

    # حصر نوع الحدث بأحرف/أرقام/فواصل (منع حقن subject NATS عشوائيّ).
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,64}", event_type or ""):
        raise HTTPException(400, "event_type غير صالح")
    subject = f"sahool.{event_type}"
    await publish_event(subject, {**data, "tenant_id": tenant_id})
    return {"published": subject}
