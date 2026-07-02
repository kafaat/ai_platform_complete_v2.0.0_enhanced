"""routers/tts.py — مسارات تحويل النصّ إلى كلام (Voices · Synthesize · Stream)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المعاملات/
الأجسام/المخرجات/المصادقة مطابقة. التبعيّات المشتركة (النماذج/المساعِدات/الحالة)
تبقى في ``main`` وتُشار إليها عبر ``main.X``. ``register_routers(app)`` يضمّ هذا
الراوتر بلا prefix.
"""

from __future__ import annotations

import main
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse

router = APIRouter()


@router.get("/tts/voices", response_model=main.VoicesResponse)
async def list_voices(_user: dict = Depends(main.get_current_user)) -> dict:
    """List all available voices + provider availability snapshot."""
    return {
        "voices": main.VOICES,
        "default": main.DEFAULT_VOICE,
        "providers": main._provider_status(),
    }


@router.get("/tts/status")
async def tts_status(_user: dict = Depends(main.get_current_user)) -> dict:
    """حالة مزوّدي TTS: لكلٍّ الاسم والتوفّر وهل هو الافتراضيّ.

    edge دائماً هو الافتراضيّ والمتوفّر؛ piper/xtts يظهران متاحين فقط حين تتوفّر
    مكتبتهما + النموذج/العلم (وإلّا available=false دون إسقاط الخدمة).
    """
    return {
        "default": main.DEFAULT_PROVIDER_NAME,
        "providers": main._provider_status(),
    }


@router.post("/tts/synthesize")
async def synthesize(
    req: main.TTSRequest,
    user: dict = Depends(main.get_current_user),
) -> Response:
    """
    Synthesize speech and return MP3 audio bytes.

    Cached by content hash for 24h to reduce API calls.
    """
    tenant_id = user.get("tenant_id", "")
    cache_key = main._cache_key(
        tenant_id,
        req.text,
        req.voice,
        req.rate,
        req.pitch,
        req.volume,
        provider=req.provider,
        normalize=req.normalize,
    )

    # Try cache first
    if main._redis:
        try:
            cached = await main._redis.get(cache_key)
            if cached:
                main.TTS_REQUESTS.labels(voice=req.voice, status="ok", cache="hit").inc()
                main.logger.info(f"Cache hit: tenant={tenant_id} voice={req.voice}")
                return Response(
                    content=cached,
                    media_type="audio/mpeg",
                    headers={
                        "X-Cache": "HIT",
                        # private: أصل TTS لكلّ مستأجِر يجب ألّا يُخزَّن في وسطاء/CDN
                        # مشتركة (تسريب عابر للمستأجرين). يبقى قابلاً للتخزين بالمتصفّح.
                        "Cache-Control": "private, max-age=86400",
                    },
                )
        except Exception as e:
            main.logger.warning(f"Redis read failed: {e}")

    # Generate
    try:
        audio = await main._generate_speech(
            req.text,
            req.voice,
            req.rate,
            req.pitch,
            req.volume,
            provider=req.provider,
            normalize=req.normalize,
        )
    except Exception as e:
        main.TTS_REQUESTS.labels(voice=req.voice, status="error", cache="miss").inc()
        main.logger.error(f"TTS generation failed: {e}")
        raise HTTPException(500, "Speech synthesis failed") from e

    # Cache result
    if main._redis:
        try:
            await main._redis.setex(cache_key, main.CACHE_TTL, audio)
        except Exception as e:
            main.logger.warning(f"Redis write failed: {e}")

    main.TTS_REQUESTS.labels(voice=req.voice, status="ok", cache="miss").inc()
    main.logger.info(
        f"Generated: tenant={tenant_id} voice={req.voice} chars={len(req.text)} bytes={len(audio)}"
    )

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "X-Cache": "MISS",
            # private: انظر مسار الـHIT أعلاه — عزل المستأجِر يمنع التخزين العامّ.
            "Cache-Control": "private, max-age=86400",
        },
    )


@router.post("/tts/stream")
async def stream(
    req: main.TTSRequest,
    user: dict = Depends(main.get_current_user),
) -> StreamingResponse:
    """Stream audio for long text (low latency, no cache)."""

    async def audio_stream():
        voice = main.VOICES[req.voice]
        communicate = main.edge_tts.Communicate(
            text=req.text,
            voice=voice,
            rate=req.rate,
            pitch=req.pitch,
            volume=req.volume,
        )
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    main.TTS_REQUESTS.labels(voice=req.voice, status="ok", cache="stream").inc()
    return StreamingResponse(audio_stream(), media_type="audio/mpeg")
