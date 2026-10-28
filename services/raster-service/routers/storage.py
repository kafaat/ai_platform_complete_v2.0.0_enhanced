"""routers/storage.py — التخزين والرفع وحزم offline (Storage/Upload/Offline)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر
the extracted modules directly. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix في نهاية ``main.py``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from raster_security_context import require_service_token
from raster_settings import OFFLINE_PACKS_DIR, RASTER_UPLOAD_MAX_BYTES, UPLOAD_DIR

router = APIRouter()
logger = logging.getLogger("raster-service")

# ST-03: الرفع يُقرأ بقطع محدودة (لا ``await file.read()`` للجسم كاملاً في الذاكرة) إلى ملفّ
# ``tmp_*`` (صنف «مؤقّت» في raster_lifecycle لو بقي يتيماً)، ثمّ يُتحقَّق منه كراستر قبل
# إعادة تسميته ذرّيّاً إلى ``.tif`` النهائيّ — فلا ``raster_url`` لبايتات ليست GeoTIFF.
_UPLOAD_CHUNK_BYTES = 1024 * 1024
# TIFF كلاسيكيّ وBigTIFF، بترتيبَي البايت.
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


def _check_georaster(path: str, label: str) -> None:
    """يفتح الملفّ بـrasterio فعلاً: GeoTIFF قابل للقراءة بنطاق واحد على الأقلّ وCRS مُعلَن."""
    import rasterio
    from rasterio.errors import RasterioError

    try:
        with rasterio.open(path) as ds:
            if ds.driver != "GTiff" or ds.count < 1 or ds.width < 1 or ds.height < 1:
                raise HTTPException(422, f"{label}_not_a_raster")
            if ds.crs is None:
                raise HTTPException(422, f"{label}_missing_crs")
    except RasterioError as e:
        raise HTTPException(422, f"{label}_not_a_raster") from e


async def _receive_georaster(file: UploadFile, raster_id: str, label: str) -> tuple[str, int]:
    """يستقبل الرفع متدفّقاً بسقف بايتات، يتحقّق منه كراستر، ثمّ يثبّته ذرّيّاً. يُرجِع (المسار، الحجم)."""
    path = os.path.join(UPLOAD_DIR, f"{raster_id}.tif")
    part = os.path.join(UPLOAD_DIR, f"tmp_{raster_id}.part")
    size = 0
    try:
        try:
            with open(part, "wb") as fh:
                while chunk := await file.read(_UPLOAD_CHUNK_BYTES):
                    if size == 0 and not chunk.startswith(_TIFF_MAGIC):
                        raise HTTPException(415, f"{label}_not_tiff")
                    size += len(chunk)
                    if size > RASTER_UPLOAD_MAX_BYTES:
                        raise HTTPException(413, f"{label}_too_large")
                    fh.write(chunk)
        except OSError as e:
            logger.warning("%s save failed: %s", label, type(e).__name__)
            raise HTTPException(500, f"{label}_save_failed") from e
        if size == 0:
            raise HTTPException(415, f"{label}_not_tiff")
        await asyncio.to_thread(_check_georaster, part, label)
        os.replace(part, path)
    finally:
        if os.path.exists(part):
            os.remove(part)
    return path, size


@router.post("/v1/upload/raster")
async def upload_raster(file: UploadFile = File(...), x_agent_token: str = Header(None)):
    """يرفع ملفّ راستر (GeoTIFF) ويُرجع raster_url داخليّاً."""
    require_service_token(x_agent_token)
    raster_id = f"ras_{uuid.uuid4().hex[:12]}"
    path, size = await _receive_georaster(file, raster_id, "raster_upload")
    logger.info(f"raster uploaded: {raster_id} ({size} bytes)")
    return {"raster_url": f"file://{path}"}


@router.post("/v1/upload/drone")
async def upload_drone(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    field_id: str | None = Form(None),
    x_agent_token: str = Header(None),
):
    """يرفع أورثوموزاييك درون (RGB عادةً — مؤشّرات VARI/GLI/TGI)."""
    require_service_token(x_agent_token)
    raster_id = f"drone_{uuid.uuid4().hex[:12]}"
    path, _size = await _receive_georaster(file, raster_id, "drone_upload")
    logger.info(f"drone uploaded: {raster_id} tenant={tenant_id}")
    return {"raster_url": f"file://{path}"}


@router.get("/v1/storage/stats")
async def storage_stats(x_agent_token: str = Header(None)):
    require_service_token(x_agent_token)
    """إحصاء التخزين (مراقبة قبل الانفجار) — حجم + توزيع بالنوع."""
    import raster_lifecycle as rl

    return rl.scan_storage(UPLOAD_DIR)


@router.post("/v1/storage/cleanup")
async def storage_cleanup(dry_run: bool = True, x_agent_token: str = Header(None)):
    """ينظّف النواتج المنتهية حسب الاحتفاظ. dry_run=true افتراضي (آمن).

    النواتج المحميّة (offline_packs) لا تُمَسّ. مرّر dry_run=false للحذف الفعلي.
    يمكن جدولته دوريّاً (scheduler) لمنع تضخّم التخزين.
    """
    require_service_token(x_agent_token)
    import raster_lifecycle as rl

    return rl.cleanup(UPLOAD_DIR, dry_run=dry_run)


@router.get("/v1/offline/packs")
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
                        "download_url": f"/v1/offline/packs/{name}",
                    }
                )
    return {
        "count": len(packs),
        "packs": packs,
        "note": "حمّل الحزمة على الجهاز لعرض خريطة الخلفيّة بلا اتّصال",
    }


@router.get("/v1/offline/packs/{pack_name}")
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
