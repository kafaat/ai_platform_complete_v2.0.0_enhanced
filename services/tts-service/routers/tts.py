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
import tts_tenant_policy
from critical_speech import CriticalSpeechError, prepare_critical_speech
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response, StreamingResponse
from providers import select_provider_for_policy

router = APIRouter()


def _prepared_text(req: main.TTSRequest) -> str:
    try:
        rendered = prepare_critical_speech(req.text, req.critical_slots)
        return main.ArabicTextNormalizer().normalize(rendered) if req.normalize else rendered
    except CriticalSpeechError as exc:
        raise HTTPException(422, detail={"error": "critical_speech_invalid"}) from exc


async def _provider_allowed_by_policy(user: dict, authorization: str | None, requested: str | None):
    """بوّابةُ السياسة الواحدة للتركيب والبثّ — تُنفَّذ **قبل** أيّ نداءٍ أو استجابة.

    TTS-LOCAL-ONLY-FALLS-BACK-TO-EXTERNAL-PROVIDER-01 · TTS-STREAM-BYPASSES-PROVIDER-SELECTION-01:
    السياسةُ من المنصّة (``tts_tenant_policy``، فشلٌ مغلق)، والمزوّدُ ممّا تسمح به وحدَه.
    لا مزوّدَ مسموح ⇒ 503 مُسمّى **بلا أيّ نداءٍ خارجيّ** (قرار المالك).
    """
    policy = await tts_tenant_policy.resolve_policy(user, authorization)
    mode = policy.mode
    chosen = select_provider_for_policy(
        requested, main._PROVIDER_REGISTRY, policy.external_allowed, policy.external_providers
    )
    if chosen is None:
        raise HTTPException(
            503,
            detail={
                "error": tts_tenant_policy.POLICY_BLOCKED_ERROR,
                "policy_mode": mode,
                "message_ar": "لا يتوفّر مزوّدُ صوتٍ تسمح به سياسةُ مشاركة البيانات لهذا المستأجِر.",
            },
        )
    return chosen


def _local_provider_failed(chosen, exc: Exception) -> HTTPException:
    main.logger.error(
        f"local TTS provider failed: provider={chosen.name} error={type(exc).__name__}"
    )
    return HTTPException(
        503,
        detail={
            "error": "local_provider_failed",
            "provider": chosen.name,
            "message_ar": "تعذّر التركيبُ بالمزوّد المحلّيّ؛ لم يُرسَل النصّ إلى أيّ مزوّدٍ خارجيّ.",
        },
    )


@router.get("/v1/tts/voices", response_model=main.VoicesResponse)
async def list_voices(_user: dict = Depends(main.get_current_user)) -> dict:
    """List all available voices + provider availability snapshot."""
    return {
        "voices": main.VOICES,
        "default": main.DEFAULT_VOICE,
        "providers": main._provider_status(),
    }


@router.get("/v1/tts/status")
async def tts_status(
    user: dict = Depends(main.get_current_user),
    authorization: str | None = Header(None),
) -> dict:
    """Provider inventory and this caller's policy eligibility, without synthesis.

    Installed providers alone do not establish speech availability. In particular,
    an installed Edge client cannot serve a local-only tenant without a local
    provider. Eligibility is a snapshot, not an audio-success guarantee; every
    synthesis/stream request independently resolves the policy again.
    """
    policy = await tts_tenant_policy.resolve_policy(user, authorization)
    chosen = select_provider_for_policy(
        None, main._PROVIDER_REGISTRY, policy.external_allowed, policy.external_providers
    )
    return {
        "default": main.DEFAULT_PROVIDER_NAME,
        "providers": main._provider_status(),
        "policy_mode": policy.mode,
        "policy_eligible_provider": chosen.name if chosen else None,
        "unavailable_reason": None if chosen else tts_tenant_policy.POLICY_BLOCKED_ERROR,
    }


@router.post("/v1/tts/synthesize")
async def synthesize(
    req: main.TTSRequest,
    user: dict = Depends(main.get_current_user),
    authorization: str | None = Header(None),
) -> Response:
    """
    Synthesize speech and return MP3 audio bytes.

    Cached by content hash for 24h to reduce API calls.
    """
    speak_text = _prepared_text(req)
    chosen = await _provider_allowed_by_policy(user, authorization, req.provider)
    tenant_id = user.get("tenant_id", "")
    cache_key = main._cache_key(
        tenant_id,
        speak_text,
        req.voice,
        req.rate,
        req.pitch,
        req.volume,
        # المزوّدُ الفعليّ لا المطلوب (صوتُ مزوّدٍ لا يُقدَّم باسم غيره)، والافتراضيّ
        # None كي تبقى مفاتيحُ المسار الافتراضيّ مطابقةً للسابق (``_cache_key``).
        provider=None if chosen.name == main.DEFAULT_PROVIDER_NAME else chosen.name,
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
                    media_type=chosen.media_type,
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
            speak_text,
            req.voice,
            req.rate,
            req.pitch,
            req.volume,
            provider=req.provider,
            normalize=False,  # Prepared once before cache lookup and provider dispatch.
            chosen=chosen,
        )
    except Exception as e:
        main.TTS_REQUESTS.labels(voice=req.voice, status="error", cache="miss").inc()
        if not chosen.external:
            raise _local_provider_failed(chosen, e) from e
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
        media_type=chosen.media_type,
        headers={
            "X-Cache": "MISS",
            # private: انظر مسار الـHIT أعلاه — عزل المستأجِر يمنع التخزين العامّ.
            "Cache-Control": "private, max-age=86400",
        },
    )


@router.post("/v1/tts/stream")
async def stream(
    req: main.TTSRequest,
    user: dict = Depends(main.get_current_user),
    authorization: str | None = Header(None),
) -> StreamingResponse:
    """Stream audio for long text (low latency, no cache).

    البوّابةُ قبل بناء الاستجابة: 503 حقيقيّ لا 200 يفشل في منتصفه (TTS-STREAM-…-01).
    """
    speak_text = _prepared_text(req)
    chosen = await _provider_allowed_by_policy(user, authorization, req.provider)

    if not chosen.external:
        # مزوّدٌ محلّيّ: لا بثَّ تدريجيّ عنده — يُركَّب كاملاً ويُبثّ دفعةً واحدة.
        try:
            audio = await main._generate_speech(
                speak_text,
                req.voice,
                req.rate,
                req.pitch,
                req.volume,
                normalize=False,
                chosen=chosen,
            )
        except Exception as e:
            main.TTS_REQUESTS.labels(voice=req.voice, status="error", cache="stream").inc()
            raise _local_provider_failed(chosen, e) from e

        async def local_stream():
            try:
                yield audio
            except Exception:
                main.TTS_REQUESTS.labels(voice=req.voice, status="error", cache="stream").inc()
                raise
            else:
                main.TTS_REQUESTS.labels(voice=req.voice, status="ok", cache="stream").inc()

        return StreamingResponse(local_stream(), media_type=chosen.media_type)

    async def audio_stream():
        voice = main.VOICES[req.voice]
        communicate = main.edge_tts.Communicate(
            text=speak_text,
            voice=voice,
            rate=req.rate,
            pitch=req.pitch,
            volume=req.volume,
        )
        sent = 0
        try:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    sent += len(chunk["data"])
                    yield chunk["data"]
        except Exception as e:
            main.TTS_REQUESTS.labels(voice=req.voice, status="error", cache="stream").inc()
            main.logger.error(
                f"TTS stream aborted after start: provider={chosen.name} "
                f"bytes_sent={sent} error={type(e).__name__}"
            )
            raise
        else:
            main.TTS_REQUESTS.labels(voice=req.voice, status="ok", cache="stream").inc()

    return StreamingResponse(audio_stream(), media_type=chosen.media_type)
