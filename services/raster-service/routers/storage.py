"""routers/storage.py — التخزين والرفع وحزم offline (Storage/Upload/Offline)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر
the extracted modules directly. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix في نهاية ``main.py``.
"""

from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from raster_security_context import require_service_token
from raster_settings import OFFLINE_PACKS_DIR, UPLOAD_DIR

router = APIRouter()
logger = logging.getLogger("raster-service")


@router.post("/upload/raster")
async def upload_raster(file: UploadFile = File(...), x_agent_token: str = Header(None)):
    """يرفع ملفّ راستر (GeoTIFF) ويُرجع raster_url داخليّاً."""
    require_service_token(x_agent_token)
    raster_id = f"ras_{uuid.uuid4().hex[:12]}"
    path = os.path.join(UPLOAD_DIR, f"{raster_id}.tif")
    try:
        content = await file.read()
        with open(path, "wb") as fh:
            fh.write(content)
    except OSError as e:
        logger.warning("raster upload save failed: %s", type(e).__name__)
        raise HTTPException(500, "raster_upload_save_failed") from e
    logger.info(f"raster uploaded: {raster_id} ({len(content)} bytes)")
    return {"raster_url": f"file://{path}"}


@router.post("/upload/drone")
async def upload_drone(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    field_id: str | None = Form(None),
    x_agent_token: str = Header(None),
):
    """يرفع أورثوموزاييك درون (RGB عادةً — مؤشّرات VARI/GLI/TGI)."""
    require_service_token(x_agent_token)
    raster_id = f"drone_{uuid.uuid4().hex[:12]}"
    path = os.path.join(UPLOAD_DIR, f"{raster_id}.tif")
    try:
        content = await file.read()
        with open(path, "wb") as fh:
            fh.write(content)
    except OSError as e:
        logger.warning("drone upload save failed: %s", type(e).__name__)
        raise HTTPException(500, "drone_upload_save_failed") from e
    logger.info(f"drone uploaded: {raster_id} tenant={tenant_id}")
    return {"raster_url": f"file://{path}"}


@router.get("/storage/stats")
async def storage_stats(x_agent_token: str = Header(None)):
    require_service_token(x_agent_token)
    """إحصاء التخزين (مراقبة قبل الانفجار) — حجم + توزيع بالنوع."""
    import raster_lifecycle as rl

    return rl.scan_storage(UPLOAD_DIR)


@router.post("/storage/cleanup")
async def storage_cleanup(dry_run: bool = True, x_agent_token: str = Header(None)):
    """ينظّف النواتج المنتهية حسب الاحتفاظ. dry_run=true افتراضي (آمن).

    النواتج المحميّة (offline_packs) لا تُمَسّ. مرّر dry_run=false للحذف الفعلي.
    يمكن جدولته دوريّاً (scheduler) لمنع تضخّم التخزين.
    """
    require_service_token(x_agent_token)
    import raster_lifecycle as rl

    return rl.cleanup(UPLOAD_DIR, dry_run=dry_run)


@router.get("/offline/packs")
async def list_offline_packs(x_agent_token: str = Header(None)):
    require_service_token(x_agent_token)
    """يسرد حزم MBTiles الجاهزة للتنزيل (الموبايل يحمّلها للعمل offline).

    صدق: يسرد ما هو موجود فعلاً على القرص فقط — لا يدّعي حزماً غير مُولَّدة.
    لتوليد حزمة: استخدم scripts_v9/generate_mbtiles.sh لمنطقة (الجوف مثلاً).
    """
    packs = []
    if os.path.isdir(OFFLINE_PACKS_DIR):
        for name in sorted(os.listdir(OFFLINE_PACKS_DIR)):
            if name.endswith((".mbtiles", ".pmtiles")):
                path = os.path.join(OFFLINE_PACKS_DIR, name)
                packs.append(
                    {
                        "name": name,
                        "format": name.rsplit(".", 1)[-1],
                        "size_mb": round(os.path.getsize(path) / 1e6, 1),
                        "download_url": f"/offline/packs/{name}",
                    }
                )
    return {
        "count": len(packs),
        "packs": packs,
        "note": "حمّل الحزمة على الجهاز لعرض خريطة الخلفيّة بلا اتّصال",
    }


@router.get("/offline/packs/{pack_name}")
async def download_offline_pack(pack_name: str, x_agent_token: str = Header(None)):
    require_service_token(x_agent_token)
    """ينزّل حزمة MBTiles/PMTiles محدّدة (للتخزين على الجهاز)."""
    # حماية من path traversal
    if "/" in pack_name or ".." in pack_name:
        raise HTTPException(400, "اسم حزمة غير صالح")
    path = os.path.join(OFFLINE_PACKS_DIR, pack_name)
    if not os.path.exists(path):
        raise HTTPException(404, "حزمة غير موجودة")

    return FileResponse(path, media_type="application/octet-stream", filename=pack_name)
