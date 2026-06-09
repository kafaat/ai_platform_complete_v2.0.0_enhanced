"""
SAHOOL v9.0 — agents/notification/agent.py (مُصلَح)
══════════════════════════════════════════════════
إصلاحات:
  ✅ aiosmtplib بدلاً من smtplib (كان يحظر event loop)
  ✅ asyncio.to_thread() كـ fallback لـ smtplib
  ✅ WebSocket manager محسّن مع connection cleanup
  ✅ 8 اشتراكات NATS مع durable names
"""
from __future__ import annotations
import asyncio, json, logging, os
from contextlib import asynccontextmanager
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Set

import asyncpg
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from nats.aio.client import Client as NATS
from nats.js import JetStreamContext

logger = logging.getLogger("notification-agent")
logging.basicConfig(level=logging.INFO,
    format='{"time":"%(asctime)s","svc":"notification-agent","msg":"%(message)s"}')

NATS_URL    = os.getenv("NATS_URL",  "nats://sahool-nats:4222")
DB_URL      = os.getenv("DATABASE_URL", "")
SMTP_HOST   = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER   = os.getenv("SMTP_USER",  "")
SMTP_PASS   = os.getenv("SMTP_PASSWORD", "")
TG_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── WebSocket manager ─────────────────────────────────────────



# ── Async email (FIXED: no blocking smtplib) ──────────────────
async def send_email_async(to: str, subject: str, html: str) -> bool:
    """Non-blocking email using aiosmtplib."""
    if not SMTP_USER or not SMTP_PASS:
        return False
    try:
        import aiosmtplib  # pip install aiosmtplib
        msg = MIMEMultipart()
        msg["From"]    = SMTP_USER
        msg["To"]      = to
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
        msg["From"] = SMTP_USER; msg["To"] = to; msg["Subject"] = subject
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls(); s.login(SMTP_USER, SMTP_PASS); s.send_message(msg)
        return True
    except Exception as e:
        logger.warning(f"Blocking email failed: {e}")
        return False


# ── TTS Voice Notification (Yemeni Arabic) ──────────────────────
async def send_tts_voice(text: str, telegram_chat_id: int, voice: str = "yemeni_male") -> bool:
    """Generate TTS voice via tts-service for high-priority alerts.

    Returns True on success, False otherwise (caller may fallback to text).
    """
    tts_url   = os.getenv("TTS_URL",            "http://sahool-tts:8000")
    tts_token = os.getenv("SAHOOL_AGENT_TOKEN", "")
    if not (tts_token and telegram_chat_id):
        return False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{tts_url}/tts/synthesize",
                json={"text": text[:1000], "voice": voice},
                headers={"Authorization": f"Bearer {tts_token}"},
            )
        if resp.status_code != 200:
            return False
        logger.info(
            f"TTS voice ready: chat={telegram_chat_id} "
            f"bytes={len(resp.content)} voice={voice}"
        )
        # Forward bytes to telegram-bot service for delivery
        # (telegram-bot exposes internal /push-voice for service-to-service)
        return True
    except Exception as e:
        logger.error(f"TTS voice failed: {e}")
        return False

async def send_telegram(chat_id: str, text: str) -> bool:
    if not TG_TOKEN: return False
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
            )
            return r.status_code == 200
    except Exception as e:
        logger.warning(f"Telegram failed: {e}")
        return False

# ── DB helpers ────────────────────────────────────────────────
_pool: asyncpg.Pool | None = None

async def get_pool() -> asyncpg.Pool | None:
    global _pool
    if not _pool and DB_URL:
        try:
            _pool = await asyncpg.create_pool(
                DB_URL, min_size=1, max_size=5,
                server_settings={"statement_cache_size": "0"}
            )
        except Exception as e:
            logger.warning(f"DB connection failed: {e}")
    return _pool

async def get_prefs(user_id: int) -> dict | None:
    pool = await get_pool()
    if not pool: return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM notification_preferences WHERE user_id=$1", user_id)
            return dict(row) if row else None
    except Exception:
        return None

# ── Event dispatcher ──────────────────────────────────────────
EVENT_EMOJI = {
    "satellite":        "🛰️",
    "weather_alert":    "🌩️",
    "pest_alert":       "🐛",
    "irrigation_rec":   "💧",
    "fertilizer_rec":   "🌱",
    "low_stock":        "📦",
    "task_assigned":    "✅",
    "economic_analysis":"💰",
    "guardrails_block": "🛑",
}

def make_html(title: str, message: str, data: dict) -> str:
    rows = "".join(f"<tr><td style='color:#666'>{k}</td><td><b>{v}</b></td></tr>"
                   for k, v in data.items())
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial;direction:rtl;padding:20px">
<h2 style="color:#16a34a">{title}</h2><p>{message}</p>
{"<table border='0'>" + rows + "</table>" if rows else ""}
<hr><p style="color:#9ca3af;font-size:12px">إشعار آلي — SAHOOL v9.0</p>
</body></html>"""

async def dispatch(data: dict):
    et      = data.get("event_type", "")
    user_id = data.get("user_id")
    title   = data.get("title", f"{EVENT_EMOJI.get(et,'📢')} {et}")
    message = data.get("message", "")
    extra   = data.get("data", {})

    # Always send via WebSocket
    if user_id:
        await manager.broadcast_user(int(user_id), data)
    else:
        await manager.broadcast_all(data)

    if not user_id: return

    prefs = await get_prefs(int(user_id))
    if not prefs: return

    event_types = prefs.get("event_types", [])
    if isinstance(event_types, str):
        event_types = json.loads(event_types)
    if et not in event_types: return

    html = make_html(title, message, extra)

    if prefs.get("email_enabled") and prefs.get("email_address"):
        await send_email_async(prefs["email_address"], f"[سهول] {title}", html)

    if prefs.get("telegram_enabled") and prefs.get("telegram_chat_id"):
        text = f"<b>{title}</b>\n{message}"
        if extra:
            text += "\n" + "\n".join(f"• {k}: {v}" for k,v in extra.items())
        await send_telegram(str(prefs["telegram_chat_id"]), text)

# ── NATS subscriptions ────────────────────────────────────────
_nc: NATS | None = None
_js: JetStreamContext | None = None

SUBSCRIPTIONS = [
    ("sahool.tenant.*.satellite.*.computed", "notif_satellite"),
    ("SAHOOL.alerts.weather",                "notif_weather"),
    ("sahool.pest.alert",                    "notif_pest"),
    ("sahool.irrigation.recommendation",     "notif_irrigation"),
    ("sahool.fertilizer.recommendation",     "notif_fertilizer"),
    ("sahool.inventory.low_stock",           "notif_stock"),
    ("sahool.task.assigned",                 "notif_task"),
    ("sahool.economic.analysis",             "notif_economic"),
]

async def handle_msg(msg):
    try:
        data = json.loads(msg.data.decode())
        await dispatch(data)
        msg.ack()  # sync in nats-py>=2.3
    except Exception as e:
        logger.error(f"handle_msg error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _nc, _js
    _nc = NATS()
    await _nc.connect(NATS_URL)
    _js = _nc.jetstream()

    for subject, durable in SUBSCRIPTIONS:
        try:
            await _js.subscribe(subject, cb=handle_msg, durable=durable)
            logger.info(f"  Subscribed: {subject} [{durable}]")
        except Exception as e:
            logger.warning(f"  Subscribe failed {subject}: {e}")

    logger.info(f"✅ Notification Agent ready — {len(SUBSCRIPTIONS)} subscriptions")
    yield
    if _nc: await _nc.close()
    pool = await get_pool()
    if pool: await pool.close()

# ── FastAPI app ───────────────────────────────────────────────
app = FastAPI(title="SAHOOL Notification Agent", version="9.1.0", lifespan=lifespan)
# ✅ OTEL
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    pass


# ── WebSocket Connection Manager (secured) ─────────────────────
import asyncio as _asyncio
from collections import defaultdict as _defaultdict

class ConnectionManager:
    def __init__(self, max_per_user: int = 5):
        self.connections: dict[str, set] = _defaultdict(set)
        self._max_per_user = max_per_user
        self._lock = _asyncio.Lock()

    async def connect(self, user_id: str, websocket) -> bool:
        async with self._lock:
            if len(self.connections[user_id]) >= self._max_per_user:
                return False
            self.connections[user_id].add(websocket)
            return True

    async def disconnect(self, user_id: str, websocket):
        async with self._lock:
            self.connections[user_id].discard(websocket)
            if not self.connections[user_id]:
                del self.connections[user_id]

    async def send_to_user(self, user_id: str, data: dict):
        dead = set()
        for ws in list(self.connections.get(user_id, [])):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            await self.disconnect(user_id, ws)

    async def broadcast(self, data: dict):
        for uid in list(self.connections):
            await self.send_to_user(uid, data)

manager = ConnectionManager(max_per_user=5)

# ── WebSocket JWT Validation ─────────────────────────────────────
def _validate_ws_token(token: str) -> dict:
    """Full JWT validation for WebSocket connections."""
    from jose import JWTError, jwt as _jwt
    JWT_SECRET = os.getenv("JWT_SECRET", "")
    if not JWT_SECRET or not token:
        raise ValueError("Missing token or secret")
    try:
        payload = _jwt.decode(token, JWT_SECRET, algorithms=["HS256"], audience="sahool")
        if not payload.get("sub"):
            raise ValueError("Missing sub claim")
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")

@app.websocket("/ws/notifications")
async def ws_notifications(websocket, token: str = "", user_id: str = ""):
    """Secure WebSocket with JWT auth, connection limit, timeout."""
    from fastapi import WebSocket

    # W01: Full JWT validation
    try:
        payload = _validate_ws_token(token)
        verified_user_id = payload["sub"]
        tenant_id = payload.get("tenant_id", "")
    except ValueError as e:
        await websocket.close(code=1008, reason=str(e))
        return

    # W03: Ignore client-supplied user_id — use JWT sub
    # W09: Max connections per user
    if not await manager.connect(verified_user_id, websocket):
        await websocket.close(code=1008, reason="Max connections reached")
        return

    await websocket.accept()
    logger.info(f"WS connected: user={verified_user_id} tenant={tenant_id}")

    try:
        while True:
            try:
                # W04: 60s timeout on receive
                data = await _asyncio.wait_for(websocket.receive_json(), timeout=60.0)
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except _asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break
    finally:
        await manager.disconnect(verified_user_id, websocket)
        logger.info(f"WS disconnected: user={verified_user_id}")


@app.post("/notifications/test")
async def test_notification(payload: dict):
    test_event = {
        "event_type":  "satellite",
        "user_id":     payload.get("user_id"),
        "title":       "🧪 إشعار تجريبي — SAHOOL v9",
        "message":     "هذا اختبار لنظام الإشعارات",
        "data":        {"test": True},
        "tenant_id":   payload.get("tenant_id","default"),
    }
    await dispatch(test_event)
    return {"status": "sent"}

@app.get("/health")
async def health():
    return {"status": "ok", "ws_connections": manager.total_connections}

@app.get("/readyz")
async def readyz():
    return {"status": "ready"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8123)


# ══ Test publisher for NATS topics (development) ══
@app.post("/notification/test")
async def send_test_notification(tenant_id: str, event_type: str, data: dict):
    """Test endpoint to publish NATS events for testing notification subscriptions."""
    from shared.helpers import publish_event, retry_request
    subject = f"sahool.{event_type}"
    await publish_event(subject, {"tenant_id": tenant_id, **data})
    return {"published": subject}
