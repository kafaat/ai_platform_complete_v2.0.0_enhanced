"""
api/imagery_automation.py — أتمتة سحب الصور الجوّية وحساب المؤشّرات

الفجوة التي يسدّها:
  raster-service يوفّر بحث الصور (/imagery/search) وحساب المؤشّرات
  (/process → NDVI/EVI/...). لكن لا شيء **يفحص دوريّاً** عن صور Sentinel
  جديدة لحقول المستخدم، ثمّ **يُطلق** حساب المؤشّرات تلقائيّاً عند توفّرها.
  دورة Sentinel-2 ~5 أيّام، فالفحص اليدوي يفوّت صوراً.

ما يفعله:
  ✓ يسجّل حقولاً (bbox + إحداثيّات) للمتابعة الدوريّة
  ✓ كلّ دورة: يبحث عن صور جديدة عبر raster-service (STAC)
  ✓ يتتبّع آخر صورة معروفة لكلّ حقل (لا يعيد معالجة القديم)
  ✓ عند صورة جديدة: يسجّلها ويطلب حساب المؤشّرات (NDVI أولويّة)
  ✓ معزول: فشل حقل لا يوقف البقيّة
  ✗ لا يعالج بكسلات هنا (raster-service يفعل) — هذا منسّق (orchestrator)
  ✗ لا يخترع حقولاً — يتابع فقط المسجّلة صراحةً

مبدأ الصدق: لو لا حقول مسجّلة → لا يضرب raster-service. ولو raster-service
غير متاح → يسجّل فشلاً واضحاً، لا يدّعي نجاحاً.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("sahool.imagery_automation")

RASTER_SERVICE_URL = os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001")
# مؤشّرات تُحسب تلقائيّاً عند صورة جديدة (دفعةً من نفس المشهد):
#   NDVI صحّة نباتيّة · NDRE نيتروجين (red-edge) · NDSI ملوحة (حرج لليمن الجافّ)
DEFAULT_INDICATORS = ["ndvi", "ndre", "ndsi"]


@dataclass
class TrackedField:
    field_id: str
    bbox: List[float]                 # [west, south, east, north]
    tenant_id: Optional[str] = None   # لتمرير الهويّة لـraster /process
    last_image_id: Optional[str] = None
    last_image_date: Optional[str] = None
    last_checked_at: Optional[str] = None
    last_indicator_job: Optional[str] = None
    new_images_found: int = 0
    check_errors: int = 0

    def to_dict(self) -> Dict:
        return {
            "field_id": self.field_id,
            "bbox": self.bbox,
            "last_image_id": self.last_image_id,
            "last_image_date": self.last_image_date,
            "last_checked_at": self.last_checked_at,
            "last_indicator_job": self.last_indicator_job,
            "new_images_found": self.new_images_found,
            "check_errors": self.check_errors,
        }


class ImageryAutomation:
    """يتابع حقولاً، يكتشف صوراً جديدة، يُطلق حساب المؤشّرات.

    التخزين: بالذاكرة افتراضيّاً، مع استمرار اختياري للقاعدة (set_pool +
    load_from_db) — لو توفّر pool. بلا pool يعمل بالذاكرة (صدق).
    """

    def __init__(self) -> None:
        self._fields: Dict[str, TrackedField] = {}
        self._pool = None

    def set_pool(self, pool) -> None:
        """يربط pool القاعدة لتمكين الاستمرار الدائم."""
        self._pool = pool

    async def load_from_db(self) -> int:
        """يحمّل الحقول المتابَعة + آخر صورة معروفة من القاعدة عند الإقلاع.

        صدق: لو لا pool، لا يفعل شيئاً ويُرجع 0. هذا يمنع إعادة معالجة صور
        سبق أن عُولجت بعد إعادة تشغيل المنصّة.
        """
        if self._pool is None:
            return 0
        loaded = 0
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT field_id, tenant_id, bbox_west, bbox_south, bbox_east, bbox_north, "
                    "last_image_id, last_image_date, last_indicator_job, "
                    "new_images_found, check_errors FROM imagery_automation_fields"
                )
                for r in rows:
                    self._fields[r["field_id"]] = TrackedField(
                        field_id=r["field_id"],
                        bbox=[r["bbox_west"], r["bbox_south"],
                              r["bbox_east"], r["bbox_north"]],
                        tenant_id=str(r["tenant_id"]) if r["tenant_id"] else None,
                        last_image_id=r["last_image_id"],
                        last_image_date=r["last_image_date"],
                        last_indicator_job=r["last_indicator_job"],
                        new_images_found=r["new_images_found"] or 0,
                        check_errors=r["check_errors"] or 0,
                    )
                    loaded += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("فشل تحميل أتمتة الصور من القاعدة: %s", e)
        return loaded

    async def _persist_field(self, tf: TrackedField) -> None:
        if self._pool is None:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO imagery_automation_fields "
                    "(field_id, tenant_id, bbox_west, bbox_south, bbox_east, bbox_north, "
                    " last_image_id, last_image_date, last_checked_at, "
                    " last_indicator_job, new_images_found, check_errors) "
                    "VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,NOW(),$9,$10,$11) "
                    "ON CONFLICT (field_id) DO UPDATE SET "
                    " tenant_id=COALESCE(EXCLUDED.tenant_id, imagery_automation_fields.tenant_id), "
                    " bbox_west=EXCLUDED.bbox_west, bbox_south=EXCLUDED.bbox_south, "
                    " bbox_east=EXCLUDED.bbox_east, bbox_north=EXCLUDED.bbox_north, "
                    " last_image_id=EXCLUDED.last_image_id, "
                    " last_image_date=EXCLUDED.last_image_date, "
                    " last_checked_at=NOW(), "
                    " last_indicator_job=EXCLUDED.last_indicator_job, "
                    " new_images_found=EXCLUDED.new_images_found, "
                    " check_errors=EXCLUDED.check_errors",
                    tf.field_id, tf.tenant_id, tf.bbox[0], tf.bbox[1], tf.bbox[2], tf.bbox[3],
                    tf.last_image_id, tf.last_image_date,
                    tf.last_indicator_job, tf.new_images_found, tf.check_errors,
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("فشل حفظ حقل الصور %s: %s", tf.field_id, e)

    def register_field(self, field_id: str, bbox: List[float],
                       tenant_id: Optional[str] = None) -> None:
        """يسجّل حقلاً للمتابعة (بالذاكرة فوراً). bbox = [west,south,east,north]."""
        if len(bbox) != 4:
            raise ValueError("bbox يجب أن يكون [west, south, east, north]")
        if field_id in self._fields:
            self._fields[field_id].bbox = bbox
            if tenant_id:
                self._fields[field_id].tenant_id = tenant_id
        else:
            self._fields[field_id] = TrackedField(
                field_id=field_id, bbox=bbox, tenant_id=tenant_id)

    async def register_field_persistent(self, field_id: str, bbox: List[float],
                                        tenant_id: Optional[str] = None) -> None:
        """يسجّل + يحفظ في القاعدة (لو توفّر pool)."""
        self.register_field(field_id, bbox, tenant_id)
        await self._persist_field(self._fields[field_id])

    def unregister_field(self, field_id: str) -> bool:
        return self._fields.pop(field_id, None) is not None

    def tracked_count(self) -> int:
        return len(self._fields)

    def status(self) -> Dict:
        return {
            "tracked_fields": len(self._fields),
            "raster_service_url": RASTER_SERVICE_URL,
            "auto_indicators": DEFAULT_INDICATORS,
            "fields": [f.to_dict() for f in self._fields.values()],
        }

    async def scan_all(self, lookback_days: int = 10) -> Dict:
        """يفحص كلّ الحقول المتابَعة عن صور جديدة (تُستدعى من scheduler).

        معزول لكلّ حقل. يُرجع ملخّص: كم حقل فُحص، كم صورة جديدة، كم فشل.
        صدق: لو لا حقول → لا يضرب raster-service.
        """
        if not self._fields:
            return {"scanned": 0, "new_images": 0, "failed": 0,
                    "note": "لا حقول مُتابَعة"}

        # استيراد متأخّر (httpx متاح في الحاوية)
        import httpx
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")

        scanned = 0
        new_images = 0
        failed = 0
        errors: List[str] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for field_id, tf in list(self._fields.items()):
                scanned += 1
                tf.last_checked_at = now.isoformat()
                try:
                    # ابحث عن صور Sentinel-2 جديدة لهذا الحقل
                    resp = await client.post(
                        f"{RASTER_SERVICE_URL}/imagery/search",
                        json={"bbox": tf.bbox, "datetime_start": start,
                              "datetime_end": end, "limit": 5},
                    )
                    resp.raise_for_status()
                    items = resp.json().get("items", [])
                    if not items:
                        continue
                    # الأحدث أوّلاً (نفترض ترتيب raster-service تنازليّاً)
                    newest = items[0]
                    newest_id = newest.get("id") or newest.get("image_id")
                    # صورة جديدة؟ (مختلفة عن آخر معروفة)
                    if newest_id and newest_id != tf.last_image_id:
                        tf.last_image_id = newest_id
                        tf.last_image_date = newest.get("datetime") or newest.get("date")
                        tf.new_images_found += 1
                        new_images += 1
                        # اطلب حساب المؤشّرات (NDVI) لو توفّر رابط الراستر
                        await self._trigger_indicators(client, tf, newest)
                        # احفظ الحالة الجديدة (لا إعادة معالجة بعد إعادة التشغيل)
                        await self._persist_field(tf)
                except Exception as e:  # noqa: BLE001 — عزل لكلّ حقل
                    failed += 1
                    tf.check_errors += 1
                    errors.append(f"{field_id}: {type(e).__name__}")
                    logger.warning("فشل فحص صور الحقل %s: %s", field_id, e)

        return {
            "scanned": scanned,
            "new_images": new_images,
            "failed": failed,
            "errors": errors[:10],
        }

    async def _trigger_indicators(self, client, tf: TrackedField, image: Dict) -> None:
        """يطلب حساب المؤشّرات لصورة جديدة عبر raster-service /process/batch.

        يحسب المؤشّرات الأساسيّة دفعةً من نفس المشهد (كفاءة): NDVI (صحّة) +
        NDRE (نيتروجين) + NDSI (ملوحة — حرج لليمن). صدق: لو لا رابط راستر
        صالح، لا يطلب (لا يدّعي معالجة).
        """
        raster_url = (
            image.get("raster_url")
            or (image.get("assets", {}) or {}).get("nir")
            or image.get("band_urls", {}).get("nir")
        )
        if not raster_url:
            # لا رابط صالح — نسجّل الصورة فقط دون معالجة (صدق)
            return
        try:
            # batch: عدّة مؤشّرات من نفس المشهد في طلب واحد (كفاءة I/O).
            # NDVI صحّة + NDRE نيتروجين + NDSI ملوحة (سياق اليمن الجافّ).
            payload = {
                "tenant_id": tf.tenant_id or "",
                "field_id": tf.field_id,
                "raster_url": raster_url,
                "indicators": DEFAULT_INDICATORS,
                "source_format": "cog",
                "bands": {"red": 1, "green": 2, "blue": 3, "nir": 4,
                          "rededge": 5, "swir1": 6, "swir2": 7},
                "scene_id": image.get("id") or image.get("image_id"),
                "capture_datetime": image.get("datetime") or image.get("date"),
            }
            resp = await client.post(
                f"{RASTER_SERVICE_URL}/process/batch", json=payload,
            )
            resp.raise_for_status()
            tf.last_indicator_job = resp.json().get("job_id")
        except Exception as e:  # noqa: BLE001
            logger.warning("فشل طلب مؤشّرات الحقل %s: %s", tf.field_id, e)


# مثيل وحيد للتطبيق
imagery_automation = ImageryAutomation()
