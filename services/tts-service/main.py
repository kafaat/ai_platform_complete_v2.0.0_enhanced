"""
SAHOOL v9.1.0 — services/tts-service/main.py
Text-to-Speech service using Microsoft Edge TTS with Yemeni Arabic voices.

Voices supported:
  - ar-YE-MaryamNeural  (Yemeni female)
  - ar-YE-SalehNeural   (Yemeni male)
  - ar-SA-HamedNeural   (Saudi male, fallback)
  - ar-EG-SalmaNeural   (Egyptian female, fallback)
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import edge_tts
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from jose import JWTError, jwt
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel, Field, field_validator

try:
    from shared.logging_config import setup_logging
    logger = setup_logging("tts-service")
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format='{"time":"%(asctime)s","svc":"tts","level":"%(levelname)s","msg":"%(message)s"}',
    )
    logger = logging.getLogger("tts-service")

VERSION       = "9.1.0"
_JWT_PUBLIC   = os.getenv("JWT_PUBLIC_KEY", "")
JWT_SECRET    = _JWT_PUBLIC if _JWT_PUBLIC else os.getenv("JWT_SECRET", "")
_JWT_ALG      = "RS256" if _JWT_PUBLIC else "HS256"
REDIS_URL     = os.getenv("REDIS_URL", "redis://sahool-redis:6379/2")
CACHE_TTL     = int(os.getenv("TTS_CACHE_TTL", "86400"))  # 24h
MAX_TEXT_LEN  = int(os.getenv("TTS_MAX_TEXT_LEN", "1000"))

# Available voices
VOICES = {
    "yemeni_female":   "ar-YE-MaryamNeural",
    "yemeni_male":     "ar-YE-SalehNeural",
    "saudi_male":      "ar-SA-HamedNeural",
    "egyptian_female": "ar-EG-SalmaNeural",
}
DEFAULT_VOICE = "yemeni_female"

# Metrics
TTS_REQUESTS = Counter(
    "sahool_tts_requests_total",
    "Total TTS requests",
    ["voice", "status", "cache"],
)
TTS_LATENCY = Histogram(
    "sahool_tts_latency_seconds",
    "TTS generation latency",
    ["voice"],
)

_redis: Optional[aioredis.Redis] = None
_security = HTTPBearer(auto_error=False)


# ── Lifespan ─────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis
    try:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=False)
        await _redis.ping()
        logger.info("✅ Redis connected for TTS cache")
    except Exception as e:
        logger.warning(f"Redis unavailable — caching disabled: {e}")
        _redis = None
    logger.info("✅ TTS service started")
    yield
    if _redis:
        await _redis.aclose()
    logger.info("TTS service stopped")


app = FastAPI(
    title="SAHOOL TTS Service (Yemeni Arabic)",
    version=VERSION,
    lifespan=lifespan,
)


# ── Auth ─────────────────────────────────────────────────────
async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_security),
) -> dict:
    """Verify JWT token and return payload."""
    if not creds:
        raise HTTPException(401, "Authentication required")
    if not JWT_SECRET:
        raise HTTPException(500, "JWT_SECRET not configured")
    try:
        return jwt.decode(
            creds.credentials,
            JWT_SECRET,
            algorithms=[_JWT_ALG],
            audience="sahool",
        )
    except JWTError as e:
        raise HTTPException(401, f"Invalid token: {e}")


# ── Models ───────────────────────────────────────────────────
class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LEN)
    voice: str = Field(default=DEFAULT_VOICE, description="Voice key from VOICES")
    rate: str = Field(default="+0%", description="Speech rate (e.g. -20%, +10%)")
    pitch: str = Field(default="+0Hz", description="Pitch adjustment")
    volume: str = Field(default="+0%", description="Volume adjustment")

    @field_validator("voice")
    @classmethod
    def validate_voice(cls, v: str) -> str:
        if v not in VOICES:
            raise ValueError(f"voice must be one of: {list(VOICES.keys())}")
        return v

    @field_validator("rate", "volume")
    @classmethod
    def validate_percent(cls, v: str) -> str:
        if not (v.endswith("%") and (v.startswith("+") or v.startswith("-"))):
            raise ValueError("rate/volume must be like '+10%' or '-20%'")
        return v


class VoicesResponse(BaseModel):
    voices: dict
    default: str


# ── Core TTS ─────────────────────────────────────────────────
def _cache_key(text: str, voice: str, rate: str, pitch: str, volume: str) -> str:
    """Generate deterministic cache key."""
    raw = f"{voice}:{rate}:{pitch}:{volume}:{text}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"sahool:tts:{digest}"


async def _generate_speech(
    text: str,
    voice_key: str,
    rate: str,
    pitch: str,
    volume: str,
) -> bytes:
    """Generate MP3 audio bytes using edge-tts."""
    voice = VOICES[voice_key]
    with TTS_LATENCY.labels(voice=voice_key).time():
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            pitch=pitch,
            volume=volume,
        )
        audio = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
        return audio.getvalue()


# ── Endpoints ────────────────────────────────────────────────
@app.get("/healthz")
@app.get("/health")
async def health() -> dict:
    return {"status": "alive", "service": "tts-service", "version": VERSION}


@app.get("/readyz")
async def readyz() -> dict:
    redis_ok = False
    if _redis:
        try:
            await _redis.ping()
            redis_ok = True
        except Exception as e:  # noqa: BLE001
            logger.debug("فحص صحّة Redis فشل: %s", type(e).__name__)
    return {
        "status": "ready",
        "redis": redis_ok,
        "voices_available": len(VOICES),
    }


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/tts/voices", response_model=VoicesResponse)
async def list_voices(_user: dict = Depends(get_current_user)) -> dict:
    """List all available voices."""
    return {"voices": VOICES, "default": DEFAULT_VOICE}


@app.post("/tts/synthesize")
async def synthesize(
    req: TTSRequest,
    user: dict = Depends(get_current_user),
) -> Response:
    """
    Synthesize speech and return MP3 audio bytes.

    Cached by content hash for 24h to reduce API calls.
    """
    tenant_id = user.get("tenant_id", "")
    cache_key = _cache_key(req.text, req.voice, req.rate, req.pitch, req.volume)

    # Try cache first
    if _redis:
        try:
            cached = await _redis.get(cache_key)
            if cached:
                TTS_REQUESTS.labels(voice=req.voice, status="ok", cache="hit").inc()
                logger.info(f"Cache hit: tenant={tenant_id} voice={req.voice}")
                return Response(
                    content=cached,
                    media_type="audio/mpeg",
                    headers={
                        "X-Cache": "HIT",
                        "Cache-Control": "public, max-age=86400",
                    },
                )
        except Exception as e:
            logger.warning(f"Redis read failed: {e}")

    # Generate
    try:
        audio = await _generate_speech(
            req.text, req.voice, req.rate, req.pitch, req.volume
        )
    except Exception as e:
        TTS_REQUESTS.labels(voice=req.voice, status="error", cache="miss").inc()
        logger.error(f"TTS generation failed: {e}")
        raise HTTPException(500, "Speech synthesis failed")

    # Cache result
    if _redis:
        try:
            await _redis.setex(cache_key, CACHE_TTL, audio)
        except Exception as e:
            logger.warning(f"Redis write failed: {e}")

    TTS_REQUESTS.labels(voice=req.voice, status="ok", cache="miss").inc()
    logger.info(
        f"Generated: tenant={tenant_id} voice={req.voice} "
        f"chars={len(req.text)} bytes={len(audio)}"
    )

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "X-Cache": "MISS",
            "Cache-Control": "public, max-age=86400",
        },
    )


@app.post("/tts/stream")
async def stream(
    req: TTSRequest,
    user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """Stream audio for long text (low latency, no cache)."""

    async def audio_stream():
        voice = VOICES[req.voice]
        communicate = edge_tts.Communicate(
            text=req.text,
            voice=voice,
            rate=req.rate,
            pitch=req.pitch,
            volume=req.volume,
        )
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    TTS_REQUESTS.labels(voice=req.voice, status="ok", cache="stream").inc()
    return StreamingResponse(audio_stream(), media_type="audio/mpeg")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
