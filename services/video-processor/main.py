#!/usr/bin/env python3
"""
SAHOOL v9.1 — Video Stream Processor
RTSP / HTTP / USB camera → frame extraction → Edge Inference
Supports: GB28181 via ZLMediaKit proxy, WebRTC, local files
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import socket
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
import numpy as np
from aiomqtt import Client as MQTTClient
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials as _Creds
from fastapi.security import HTTPBearer as _Bearer
from jose import JWTError as _v_JE
from jose import jwt as _v_jwt
from pydantic import BaseModel, Field, field_validator

# ── حارس SSRF لمصادر البثّ ────────────────────────────────────
# الخدمة تتّصل بكاميرات ميدانيّة تعيش غالباً على شبكات LAN خاصّة، فلا نحظر
# النطاقات الخاصّة (يكسر الاستخدام المشروع). نحظر فقط loopback وlink-local
# (عنوان ميتاداتا السحابة 169.254.169.254) وغير المحدّد/المحجوز/البثّ الجماعيّ،
# والمخطّطات غير البثّيّة (file:// وغيره) — وهي ناقلات SSRF الحقيقيّة.
_ALLOWED_STREAM_SCHEMES = {"rtsp", "rtsps", "http", "https"}


def _validate_stream_source(url: str) -> None:
    """يرفع ValueError إن كان رابط البثّ خطر SSRF (مخطّط ممنوع/مضيف داخليّ محظور)."""
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError("رابط بثّ غير صالح") from e
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_STREAM_SCHEMES:
        raise ValueError(f"مخطّط غير مسموح: {scheme or '?'} (المسموح: rtsp/rtsps/http/https)")
    host = parsed.hostname
    if not host:
        raise ValueError("رابط بثّ بلا مضيف")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError("تعذّر تحليل مضيف الرابط") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_loopback
            or ip.is_link_local  # يشمل 169.254.169.254 (ميتاداتا السحابة)
            or ip.is_unspecified
            or ip.is_multicast
            or ip.is_reserved
        ):
            raise ValueError("الرابط يشير إلى عنوان داخليّ محظور (loopback/link-local/metadata)")


try:
    from shared.logging_config import setup_logging

    logger = setup_logging("video-processor")
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format='{"time":"%(asctime)s","svc":"video-processor","msg":"%(message)s"}',
    )
    logger = logging.getLogger("video-processor")

# ── Config ────────────────────────────────────────────────────
MQTT_BROKER_URL = os.getenv("MQTT_BROKER_URL", "mqtt://sahool-fastbee:1883")


def _parse_mqtt_broker_url(url: str) -> tuple[str, int]:
    """يستخرج (hostname, port) من mqtt://host:port — aiomqtt.Client يحتاج المضيف
    والمنفذ لا URL كاملاً (تمرير URL كاملاً كـhostname يفشل في DNS)."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return (parsed.hostname or "localhost"), (parsed.port or 1883)


def _mqtt_disabled() -> bool:
    """MQTT معطّل إذا لم يُضبط العنوان أو بدأ بـ'disabled' — للتشغيل بلا وسيط."""
    return not MQTT_BROKER_URL or MQTT_BROKER_URL.startswith("disabled")


EDGE_INFERENCE_URL = os.getenv("EDGE_INFERENCE_URL", "http://sahool-edge:8000")
ZLMEDIA_API_URL = os.getenv(
    "ZLMEDIA_API_URL", os.getenv("ZLMEDIAKIT_URL", "http://sahool-zlmediakit:8080")
)
REDIS_URL = os.getenv("REDIS_URL", "")
FRAME_INTERVAL_SEC = int(os.getenv("FRAME_INTERVAL_SEC", "5"))
MAX_CONCURRENT_STREAMS = int(os.getenv("MAX_CONCURRENT_STREAMS", "10"))


# ══════════════════════════════════════════════════════════════
# Video Stream Manager
# ══════════════════════════════════════════════════════════════
class StreamConfig(BaseModel):
    stream_id: str
    rtsp_url: str | None = None
    http_url: str | None = None
    usb_index: int | None = None
    field_id: str = "unknown"
    tenant_id: str = "default"
    ai_enabled: bool = True
    ai_model: str = "pest_yolov8"
    detection_interval_sec: int = 5


class StreamState:
    def __init__(self, config: StreamConfig):
        self.config = config
        self.task: asyncio.Task | None = None
        self.last_frame: np.ndarray | None = None
        self.last_detection: dict | None = None
        self.status = "inactive"
        self.error_count = 0
        self.frame_count = 0


STREAMS: dict[str, StreamState] = {}


# ══════════════════════════════════════════════════════════════
# Frame Capture (OpenCV)
# ══════════════════════════════════════════════════════════════
def capture_frame(source: str) -> np.ndarray | None:
    """Capture a single frame from RTSP/HTTP/USB. Blocking — run in thread pool."""
    try:
        import cv2

        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            return None
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None:
            return frame
    except Exception as e:
        logger.warning(f"Capture error: {e}")
    return None


async def async_capture(source: str) -> np.ndarray | None:
    return await asyncio.to_thread(capture_frame, source)


# ══════════════════════════════════════════════════════════════
# Edge Inference Call
# ══════════════════════════════════════════════════════════════
async def run_inference(frame: np.ndarray, model: str = "pest_yolov8") -> dict:
    """Send frame to edge-inference service."""
    import cv2

    success, encoded = cv2.imencode(".jpg", frame)  # MED-VIDEO-01
    if not success:
        return {"error": "encode_failed"}

    files = {"file": ("frame.jpg", encoded.tobytes(), "image/jpeg")}
    # edge /inference/pest-detect يتوقّع حقول Form مسطّحة (لا json متداخل) + توكن الخدمة
    data = {
        "field_id": "stream",
        "crop": "wheat",
        "confidence_threshold": "0.6",
        "return_image": "false",
    }
    headers = {"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", "")}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{EDGE_INFERENCE_URL}/inference/pest-detect",
                data=data,
                files=files,
                headers=headers,
            )
            if resp.status_code in (401, 403, 503):
                # فشل مصادقة/تفويض الخدمة — لا نبتلعه بصمت كنجاح
                logger.warning(
                    "Edge inference auth failed: status=%s body=%s",
                    resp.status_code,
                    resp.text[:200],
                )
                return {"error": f"auth_failed:{resp.status_code}"}
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning(f"Inference call failed: {e}")
        return {"error": str(e)}


# ══════════════════════════════════════════════════════════════
# Stream Processing Loop
# ══════════════════════════════════════════════════════════════
async def process_stream_loop(stream_id: str):
    state = STREAMS[stream_id]
    cfg = state.config

    # Determine source
    source = cfg.rtsp_url or cfg.http_url or str(cfg.usb_index or 0)
    if cfg.rtsp_url and cfg.rtsp_url.startswith("rtsp://"):
        # If ZLMediaKit proxy available, use HTTP-FLV instead of raw RTSP
        try:
            proxy_url = f"{ZLMEDIA_API_URL}/index/api/addStreamProxy"
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.post(
                    proxy_url,
                    json={
                        "vhost": "__defaultVhost__",
                        "app": "live",
                        "stream": stream_id,
                        "url": cfg.rtsp_url,
                    },
                )
                if r.status_code == 200:
                    source = f"{ZLMEDIA_API_URL}/live/{stream_id}.live.flv"
                    logger.info(f"[{stream_id}] ZLMediaKit proxy active: {source}")
        except Exception as e:  # noqa: BLE001
            logger.debug("ZLMediaKit proxy تعذّر [%s]: %s", stream_id, type(e).__name__)

    state.status = "active"
    last_detection_time = 0.0

    while state.status == "active":
        try:
            frame = await async_capture(source)
            if frame is None:
                state.error_count += 1
                if state.error_count > 10:
                    logger.error(f"[{stream_id}] Too many capture failures, stopping")
                    state.status = "error"
                    break
                await asyncio.sleep(5)
                continue

            state.error_count = 0
            state.frame_count += 1
            state.last_frame = frame

            now = time.time()
            if cfg.ai_enabled and (now - last_detection_time) >= cfg.detection_interval_sec:
                result = await run_inference(frame, cfg.ai_model)
                state.last_detection = result
                last_detection_time = now

                # Publish alert via MQTT if high-confidence pest found
                detections = result.get("detections", [])
                high_conf = [d for d in detections if d.get("confidence", 0) > 0.8]
                if high_conf:
                    await publish_alert(cfg, high_conf)

            await asyncio.sleep(FRAME_INTERVAL_SEC)

        except asyncio.CancelledError:
            state.status = "inactive"
            break
        except Exception as e:
            logger.error(f"[{stream_id}] Loop error: {e}")
            await asyncio.sleep(5)

    logger.info(f"[{stream_id}] Stream loop ended")


async def publish_alert(cfg: StreamConfig, detections: list):
    """Publish pest alert to MQTT broker (FastBee)."""
    if _mqtt_disabled():
        logger.debug("MQTT معطّل — تخطّي نشر تنبيه الآفة")
        return
    try:
        topic = f"sahool/tenant/{cfg.tenant_id}/alerts/pest"
        payload = json.dumps(
            {
                "stream_id": cfg.stream_id,
                "field_id": cfg.field_id,
                "detections": detections,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            ensure_ascii=False,
        )
        host, port = _parse_mqtt_broker_url(MQTT_BROKER_URL)
        async with MQTTClient(host, port=port) as client:
            await client.publish(topic, payload, qos=1)
    except Exception as e:
        logger.warning(f"MQTT publish failed: {e}")


# ══════════════════════════════════════════════════════════════
# Lifespan
# ══════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🎥 Video Processor starting — RTSP/HTTP/USB ready")
    yield
    # Cleanup
    for _sid, state in list(STREAMS.items()):
        state.status = "inactive"
        if state.task:
            state.task.cancel()
    logger.info("🎥 Video Processor stopped")


# HIGH-VIDEO-01 FIX: JWT authentication
_v_bearer = _Bearer(auto_error=False)
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ التوكن (تدقيق B: iss لم يُفحَص).
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}


async def _get_current_user(creds: _Creds = Depends(_v_bearer)) -> dict:
    """Verify JWT and return user payload."""
    if not creds:
        raise HTTPException(401, "Authentication required")
    try:
        _v_pub = os.getenv("JWT_PUBLIC_KEY", "")
        payload = _v_jwt.decode(
            creds.credentials,
            _v_pub or os.getenv("JWT_SECRET", ""),
            algorithms=["RS256" if _v_pub else "HS256"],
            audience="sahool",
        )
    except _v_JE as e:
        raise HTTPException(401, "Invalid token") from e
    # تدقيق B: افرض المُصدِر بعد فكّ ناجح — مُصدِر مجهول ⇒ 401 كتوكن غير صالح.
    if payload.get("iss") not in _ALLOWED_ISS:
        raise HTTPException(401, "Invalid token")
    return payload


def _assert_stream_tenant(state: StreamState, user: dict) -> None:
    """يمنع IDOR عبر المستأجرين: مالك غير admin يرى بثّ مستأجِره فقط. 404 عند
    عدم التطابق (لا 403) كي لا يُكشَف وجود الـstream عبر المستأجرين."""
    if user.get("role") == "admin":
        return
    if str(state.config.tenant_id) != str(user.get("tenant_id", "")):
        raise HTTPException(404, "Stream not found")


# from shared.helpers import get_current_user
app = FastAPI(title="SAHOOL Video Processor", version="9.1.0", lifespan=lifespan)


# ══════════════════════════════════════════════════════════════
# API Endpoints
# ══════════════════════════════════════════════════════════════
class CreateStreamRequest(BaseModel):
    stream_id: str = Field(
        default_factory=lambda: f"stream_{uuid.uuid4().hex[:12]}"
    )  # MED-VIDEO-03
    rtsp_url: str | None = None
    http_url: str | None = None
    usb_index: int | None = None
    field_id: str = "unknown"
    tenant_id: str = "default"
    ai_enabled: bool = True
    ai_model: str = "pest_yolov8"
    detection_interval_sec: int = 5

    @field_validator("rtsp_url", "http_url")
    @classmethod
    def _check_source(cls, v: str | None) -> str | None:
        # حارس SSRF: يُرفض الرابط الخطر بـ422 قبل تمريره لـZLMediaKit/cv2.VideoCapture
        if v:
            _validate_stream_source(v)
        return v


@app.post("/streams")
async def create_stream(req: CreateStreamRequest, user: dict = Depends(_get_current_user)):
    if req.stream_id in STREAMS:
        raise HTTPException(409, "Stream already exists")
    if len(STREAMS) >= MAX_CONCURRENT_STREAMS:
        raise HTTPException(503, "Max concurrent streams reached")

    cfg = StreamConfig(**req.model_dump())
    state = StreamState(cfg)
    STREAMS[req.stream_id] = state
    state.task = asyncio.create_task(process_stream_loop(req.stream_id))

    return {
        "stream_id": req.stream_id,
        "status": "starting",
        "source": cfg.rtsp_url or cfg.http_url or f"usb:{cfg.usb_index}",
    }


@app.delete("/streams/{stream_id}")
async def stop_stream(stream_id: str, user: dict = Depends(_get_current_user)):
    state = STREAMS.pop(stream_id, None)
    if not state:
        raise HTTPException(404, "Stream not found")
    state.status = "inactive"
    if state.task:
        state.task.cancel()
    return {"stream_id": stream_id, "status": "stopped"}


@app.get("/streams/{stream_id}")
async def get_stream(stream_id: str, user: dict = Depends(_get_current_user)):
    state = STREAMS.get(stream_id)
    if not state:
        raise HTTPException(404, "Stream not found")
    # تقييد بالمستأجِر: المنفذ كان بلا مصادقة ويُرجِع rtsp_url (قد يحوي اعتماد كاميرا)
    _assert_stream_tenant(state, user)
    return {
        "stream_id": stream_id,
        "status": state.status,
        "frame_count": state.frame_count,
        "last_detection": state.last_detection,
        "config": state.config.model_dump(),
    }


@app.get("/streams")
async def list_streams(user: dict = Depends(_get_current_user)):
    # تقييد بالمستأجِر: كان بلا مصادقة ويعدّد بثوث كلّ المستأجرين + مصادرها
    is_admin = user.get("role") == "admin"
    tid = str(user.get("tenant_id", ""))
    return {
        "streams": [
            {
                "stream_id": sid,
                "status": s.status,
                "frame_count": s.frame_count,
                "source": s.config.rtsp_url or s.config.http_url or f"usb:{s.config.usb_index}",
            }
            for sid, s in STREAMS.items()
            if is_admin or str(s.config.tenant_id) == tid
        ],
        "max_streams": MAX_CONCURRENT_STREAMS,
    }


@app.post("/streams/{stream_id}/snapshot")
async def snapshot(stream_id: str, user: dict = Depends(_get_current_user)):
    state = STREAMS.get(stream_id)
    if not state or state.last_frame is None:
        raise HTTPException(404, "No frame available")
    # تقييد بالمستأجِر: كان بلا مصادقة ويُرجِع لقطة كاميرا حيّة لأيّ طالب
    _assert_stream_tenant(state, user)
    import cv2

    success2, buf = cv2.imencode(".jpg", state.last_frame)  # MED-VIDEO-01
    from fastapi.responses import Response

    return Response(content=buf.tobytes(), media_type="image/jpeg")


@app.get("/healthz")
@app.get("/health")
async def health():
    return {
        "status": "alive",
        "active_streams": sum(1 for s in STREAMS.values() if s.status == "active"),
        "max_streams": MAX_CONCURRENT_STREAMS,
    }


@app.get("/readyz")
async def readyz():
    # بلا تبعيّة صلبة قصداً: لا pool قاعدة ولا عميل Redis متّصل (REDIS_URL غير
    # مُستهلَك هنا). النشر عبر MQTT والنداءات الخلفيّة (edge/zlmedia) محاولة-أفضل
    # لا تُعطِّل الإقلاع. لا شيء صلب ننتظره ⇒ جاهز بصدق.
    return {"status": "ready", "version": "9.1.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
