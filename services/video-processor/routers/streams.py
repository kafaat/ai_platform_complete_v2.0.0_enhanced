"""routers/streams.py — إدارة بثوث الفيديو (Streams)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المخرجات/
المصادقة مطابقة. التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main``
وتُشار إليها عبر ``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import main
from fastapi import APIRouter, Depends, HTTPException
from stream_events import build_stream_event, emit_stream_event
from stream_registry import StreamRegistry
from zlmedia_client import ZLMediaKitClient

router = APIRouter()

# ── سجلّ البثوث النشِط + عميل ZLMediaKit (حالة على مستوى الوحدة) ──────────
# سجلّ في الذاكرة معزول بالمستأجِر يواكب STREAMS (الأخير يحمل StreamState الثقيل
# لحلقة الالتقاط؛ هذا السجلّ الخفيف يخدم عقود اللقطة/التسجيل/الأحداث). خيطيّ الأمان.
registry = StreamRegistry()


def _client() -> ZLMediaKitClient:
    """يبني عميل ZLMediaKit من إعداد main الحاليّ (يعيد استخدام الرابط/السرّ).

    دالّة كي يقرأ الإعداد الطازج ويسهل استبداله في الاختبار (monkeypatch)."""
    return ZLMediaKitClient(base_url=main.ZLMEDIA_API_URL, secret=main.ZLMEDIAKIT_API_SECRET)


def _assert_registry_tenant(entry, user: dict) -> None:
    """عزل المستأجرين لقيود السجلّ: 404 إن غاب القيد أو اختلف المستأجِر
    (لا 403 — كي لا يُكشَف وجود البثّ عبر المستأجرين). fail-closed مطابق
    لـ``main._assert_stream_tenant``."""
    token_tenant = main._token_tenant(user)
    if entry is None or not token_tenant or str(entry.tenant_id) != token_tenant:
        raise HTTPException(404, "Stream not found")


@router.post("/v1/streams")
async def create_stream(
    req: main.CreateStreamRequest, user: dict = Depends(main._get_current_user)
):
    if req.stream_id in main.STREAMS:
        raise HTTPException(409, "Stream already exists")
    if len(main.STREAMS) >= main.MAX_CONCURRENT_STREAMS:
        raise HTTPException(503, "Max concurrent streams reached")

    # عزل المستأجرين: tenant_id يُشتقّ من مطالبة الرمز المُتحقَّق منه — لا يُوثَق به
    # من جسم الطلب أبداً (مثل raster/soil: الملكيّة تُربَط بالرمز عند الإنشاء).
    token_tenant = main._token_tenant(user)
    if not token_tenant:
        # fail-closed: رمز بلا مستأجِر لا يستطيع امتلاك بثّ.
        raise HTTPException(403, "Token has no tenant_id")
    body = req.model_dump()
    body_tenant = str(body.get("tenant_id", "") or "")
    # رفض tenant_id متعارض في الجسم (لا تجاوز صامت) — وإلّا اربط بمستأجِر الرمز.
    if body_tenant and body_tenant != "default" and body_tenant != token_tenant:
        raise HTTPException(403, "tenant_id mismatch: body must not override token tenant")
    body["tenant_id"] = token_tenant  # الربط الموثوق

    cfg = main.StreamConfig(**body)
    state = main.StreamState(cfg)
    main.STREAMS[req.stream_id] = state
    state.task = asyncio.create_task(main.process_stream_loop(req.stream_id))

    source = cfg.rtsp_url or cfg.http_url or f"usb:{cfg.usb_index}"
    # قيّد البثّ في السجلّ الخفيف وابثّ حدث البدء (best-effort — لا يُسقِط الإنشاء).
    entry = registry.register(
        stream_id=req.stream_id,
        tenant_id=token_tenant,
        source_url=source,
        created_at=datetime.now(UTC).isoformat(),
        state="pending",
        last_event="stream.started",
    )
    await emit_stream_event(build_stream_event("stream.started", entry, ts=entry.created_at))

    return {
        "stream_id": req.stream_id,
        "status": "starting",
        "source": source,
    }


@router.delete("/v1/streams/{stream_id}")
async def stop_stream(stream_id: str, user: dict = Depends(main._get_current_user)):
    # عزل المستأجرين: لا تُزِل البثّ من الذاكرة قبل إثبات ملكيّة مستأجِر الرمز.
    # كان pop() قبل _assert_stream_tenant يسمح لمستأجِر آخر بإيقاف/حذف بثّ لا يملكه
    # عبر معرفة stream_id فقط. الفشل الآن 404 ويبقى بثّ المالك سليماً.
    state = main.STREAMS.get(stream_id)
    if not state:
        raise HTTPException(404, "Stream not found")
    main._assert_stream_tenant(state, user)
    main.STREAMS.pop(stream_id, None)
    state.status = "inactive"
    if state.task:
        state.task.cancel()
    # زامِن السجلّ الخفيف وابثّ حدث الإيقاف (best-effort).
    entry = registry.update_state(stream_id, "stopped", last_event="stream.stopped")
    registry.remove(stream_id)
    if entry is not None:
        await emit_stream_event(build_stream_event("stream.stopped", entry, ts=entry.created_at))
    return {"stream_id": stream_id, "status": "stopped"}


@router.get("/v1/streams/{stream_id}")
async def get_stream(stream_id: str, user: dict = Depends(main._get_current_user)):
    state = main.STREAMS.get(stream_id)
    if not state:
        raise HTTPException(404, "Stream not found")
    # تقييد بالمستأجِر: المنفذ كان بلا مصادقة ويُرجِع rtsp_url (قد يحوي اعتماد كاميرا)
    main._assert_stream_tenant(state, user)
    # لا نُسرّب اعتماد الكاميرا (rtsp/http URL قد يحوي user:pass) في ردّ الحالة.
    cfg = state.config.model_dump()
    cfg.pop("rtsp_url", None)
    cfg.pop("http_url", None)
    return {
        "stream_id": stream_id,
        "status": state.status,
        "frame_count": state.frame_count,
        "last_detection": state.last_detection,
        "config": cfg,
        "source_configured": bool(
            state.config.rtsp_url or state.config.http_url or state.config.usb_index is not None
        ),
    }


@router.get("/v1/streams")
async def list_streams(user: dict = Depends(main._get_current_user)):
    # تقييد بالمستأجِر: كلّ مستأجِر يرى بثوثه فقط. لا تجاوز admin شامل (أُزيل):
    # admin المستأجِر محصور في مستأجِره؛ العبور المشروع عبر break-glass فقط.
    # fail-closed: رمز بلا مستأجِر ⇒ لا شيء (tid فارغ لا يطابق أيّ بثّ مملوك).
    tid = main._token_tenant(user)
    return {
        "streams": [
            {
                "stream_id": sid,
                "status": s.status,
                "frame_count": s.frame_count,
                "source_configured": bool(
                    s.config.rtsp_url or s.config.http_url or s.config.usb_index is not None
                ),
                "source_type": "rtsp"
                if s.config.rtsp_url
                else ("http" if s.config.http_url else "usb"),
            }
            for sid, s in main.STREAMS.items()
            if tid and str(s.config.tenant_id) == tid
        ],
        "max_streams": main.MAX_CONCURRENT_STREAMS,
    }


@router.post("/v1/streams/{stream_id}/snapshot")
async def snapshot(stream_id: str, user: dict = Depends(main._get_current_user)):
    state = main.STREAMS.get(stream_id)
    if not state or state.last_frame is None:
        raise HTTPException(404, "No frame available")
    # تقييد بالمستأجِر: كان بلا مصادقة ويُرجِع لقطة كاميرا حيّة لأيّ طالب
    main._assert_stream_tenant(state, user)
    import cv2

    success2, buf = cv2.imencode(".jpg", state.last_frame)  # MED-VIDEO-01
    from fastapi.responses import Response

    return Response(content=buf.tobytes(), media_type="image/jpeg")


# ══════════════════════════════════════════════════════════════
# لقطة ZLMediaKit + تسجيل (عقود العميل + السجلّ الخفيف + الأحداث)
# ══════════════════════════════════════════════════════════════
@router.get("/v1/streams/{stream_id}/snapshot")
async def snapshot_zlm(stream_id: str, user: dict = Depends(main._get_current_user)):
    """لقطة عبر ZLMediaKit (getSnap). 404 إن كان البثّ مجهولاً في السجلّ.

    (نظير POST /v1/streams/{stream_id}/snapshot الذي يُرجِع آخر إطار مُلتقَط محليّاً؛
    هذا يستدعي خادم الوسائط.)
    """
    entry = registry.get(stream_id)
    _assert_registry_tenant(entry, user)
    # النداء متزامن (httpx.Client) — نُشغّله في خيط كي لا نحجب حلقة الأحداث.
    result = await asyncio.to_thread(_client().snapshot, stream_id)
    content = result.get("content")
    if result.get("ok") and content:
        from fastapi.responses import Response

        return Response(
            content=content,
            media_type=result.get("content_type") or "image/jpeg",
        )
    # فشل ليّن: نُعيد الميتاداتا (لا نرفع) كي يقرّر العميل.
    return {"stream_id": stream_id, "snapshot": result}


@router.post("/v1/streams/{stream_id}/record/start")
async def record_start(stream_id: str, user: dict = Depends(main._get_current_user)):
    """يبدأ تسجيل البثّ عبر ZLMediaKit ويحدّث السجلّ + يبثّ الحدث.

    نجاح ⇒ الحالة ``recording`` + ``recording.started``؛ فشل العميل ⇒ ``error`` +
    ``stream.error`` (fail-soft: لا نرفع على 4xx/5xx من خادم الوسائط)."""
    entry = registry.get(stream_id)
    _assert_registry_tenant(entry, user)
    result = await asyncio.to_thread(_client().start_record, stream_id)
    if result.get("ok"):
        updated = registry.update_state(stream_id, "recording", last_event="recording.started")
        await emit_stream_event(
            build_stream_event("recording.started", updated, ts=updated.created_at)
        )
        return {"stream_id": stream_id, "state": "recording", "ok": True, "result": result}
    updated = registry.update_state(stream_id, "error", last_event="stream.error")
    await emit_stream_event(build_stream_event("stream.error", updated, ts=updated.created_at))
    return {"stream_id": stream_id, "state": "error", "ok": False, "result": result}


@router.post("/v1/streams/{stream_id}/record/stop")
async def record_stop(stream_id: str, user: dict = Depends(main._get_current_user)):
    """يوقف تسجيل البثّ عبر ZLMediaKit ويحدّث السجلّ + يبثّ الحدث.

    نجاح ⇒ الحالة ``live`` + ``recording.stopped``؛ فشل العميل ⇒ ``error`` +
    ``stream.error`` (fail-soft)."""
    entry = registry.get(stream_id)
    _assert_registry_tenant(entry, user)
    result = await asyncio.to_thread(_client().stop_record, stream_id)
    if result.get("ok"):
        updated = registry.update_state(stream_id, "live", last_event="recording.stopped")
        await emit_stream_event(
            build_stream_event("recording.stopped", updated, ts=updated.created_at)
        )
        return {"stream_id": stream_id, "state": "live", "ok": True, "result": result}
    updated = registry.update_state(stream_id, "error", last_event="stream.error")
    await emit_stream_event(build_stream_event("stream.error", updated, ts=updated.created_at))
    return {"stream_id": stream_id, "state": "error", "ok": False, "result": result}
