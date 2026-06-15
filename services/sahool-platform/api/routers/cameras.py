"""api/routers/cameras.py — مراقبة الحقول بالكاميرا (Field Cameras)
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّتان حرفيّاً مع تغيير ``@app`` إلى ``@router``. عين
ميدانيّة — لا كشف آلي بالـML.

الدوالّ/الأصناف النقيّة (``api.field_cameras``) تُستورَد مباشرةً من وحدتها — وهي نفس
الكائنات التي كانت في ``main`` (لا تُبقى استيراداً يتيماً هناك). أمّا التبعيات/النماذج
المُعرَّفة في ``main`` فتبقى هناك وتُستورَد من ``api.main`` حفظاً
لـ``_rebuild_pydantic_models`` واستيرادات الاختبارات. لتفادي الاستيراد الدائريّ:
``api.main`` يستورد هذا الموجِّه في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.field_cameras import (
    CameraSnapshot,
    link_snapshot_as_evidence,
    register_camera,
)
from api.main import (
    Permission,
    RegisterCameraRequest,
    SnapshotEvidenceRequest,
    UserSchema,
    require_permission,
)

router = APIRouter()


@router.post("/api/v1/cameras/register")
def cameras_register(
    req: RegisterCameraRequest,
    user: UserSchema = Depends(require_permission(Permission.DEVICE_MANAGE)),
):
    """يسجّل كاميرا مراقبة لحقل (عين ميدانيّة — لا كشف آلي بالذكاء الاصطناعي)."""
    try:
        return register_camera(
            req.camera_id,
            req.field_id,
            req.name_ar,
            req.camera_type,
            lat=req.lat,
            lon=req.lon,
            capture_interval_min=req.capture_interval_min,
            note_ar=req.note_ar,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/api/v1/cameras/snapshot-evidence")
def cameras_snapshot_evidence(
    req: SnapshotEvidenceRequest,
    user: UserSchema = Depends(require_permission(Permission.DEVICE_MANAGE)),
):
    """يحوّل لقطة كاميرا إلى قرينة ميدانيّة (field_obs) للتظافر — لا تشخيص آلي."""
    snap = CameraSnapshot(
        snapshot_id=req.snapshot_id,
        camera_id=req.camera_id,
        field_id=req.field_id,
        media_uri=req.media_uri,
        captured_at=req.captured_at,
        linked_pin_id=req.linked_pin_id,
        note_ar=req.note_ar,
    )
    return link_snapshot_as_evidence(snap)
