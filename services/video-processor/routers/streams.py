"""routers/streams.py — إدارة بثوث الفيديو (Streams)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المخرجات/
المصادقة مطابقة. التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main``
وتُشار إليها عبر ``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import asyncio

import main
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.post("/streams")
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

    return {
        "stream_id": req.stream_id,
        "status": "starting",
        "source": cfg.rtsp_url or cfg.http_url or f"usb:{cfg.usb_index}",
    }


@router.delete("/streams/{stream_id}")
async def stop_stream(stream_id: str, user: dict = Depends(main._get_current_user)):
    state = main.STREAMS.pop(stream_id, None)
    if not state:
        raise HTTPException(404, "Stream not found")
    state.status = "inactive"
    if state.task:
        state.task.cancel()
    return {"stream_id": stream_id, "status": "stopped"}


@router.get("/streams/{stream_id}")
async def get_stream(stream_id: str, user: dict = Depends(main._get_current_user)):
    state = main.STREAMS.get(stream_id)
    if not state:
        raise HTTPException(404, "Stream not found")
    # تقييد بالمستأجِر: المنفذ كان بلا مصادقة ويُرجِع rtsp_url (قد يحوي اعتماد كاميرا)
    main._assert_stream_tenant(state, user)
    return {
        "stream_id": stream_id,
        "status": state.status,
        "frame_count": state.frame_count,
        "last_detection": state.last_detection,
        "config": state.config.model_dump(),
    }


@router.get("/streams")
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
                "source": s.config.rtsp_url or s.config.http_url or f"usb:{s.config.usb_index}",
            }
            for sid, s in main.STREAMS.items()
            if tid and str(s.config.tenant_id) == tid
        ],
        "max_streams": main.MAX_CONCURRENT_STREAMS,
    }


@router.post("/streams/{stream_id}/snapshot")
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
