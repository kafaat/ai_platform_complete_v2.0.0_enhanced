"""
api/imagery_automation.py — أتمتة سحب الصور الجوّية وحساب المؤشّرات

الفجوة التي يسدّها:
  raster-service يوفّر بحث الصور (/v1/imagery/search) وحساب المؤشّرات
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

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from api.raster_service_client import (
    get_best_imagery_scene,
    get_job_result,
    get_job_status,
    process_field_cdse,
    process_field_from_stac,
    process_indicator_batch,
    raster_service_url,
    search_imagery_scenes,
)

logger = logging.getLogger("sahool.imagery_automation")

# حالات المهمّة **النهائيّة** في raster-service (`raster_api_models.JobStatus`): بعدها لا
# يتغيّر شيء، فالانتظار بعدها انتظار بلا نهاية. `processed_unpublished` نهائيّة أيضاً —
# نجاح معالجة بلا إدامة — وإغفالها كان سيُنتِج انتظاراً حتّى نفاد المهلة في كلّ دورة
# تعمل بوضع الإدامة «أفضل-جهد».
_BATCH_TERMINAL_STATUSES = frozenset({"completed", "processed_unpublished", "failed", "cancelled"})


def _batch_wait_budget_s() -> float:
    """أقصى انتظار لاكتمال دفعة واحدة (ثوانٍ). صفر أو أقلّ ⇒ لا انتظار (سلوك ما قبل الإصلاح)."""
    try:
        return float(os.getenv("IMAGERY_BATCH_WAIT_BUDGET_S", "120"))
    except ValueError:
        return 120.0


def _batch_poll_interval_s() -> float:
    """الفاصل بين استطلاعين. يُقيَّد بحدّ أدنى كي لا يتحوّل الاستطلاع إلى حلقة مشغولة."""
    try:
        return max(0.05, float(os.getenv("IMAGERY_BATCH_POLL_INTERVAL_S", "2")))
    except ValueError:
        return 2.0


# مؤشّرات تُحسب تلقائيّاً عند صورة جديدة (دفعةً من نفس المشهد):
#   NDVI صحّة نباتيّة · NDRE نيتروجين (red-edge) · NDSI ملوحة (حرج لليمن الجافّ)
#   NDMI رطوبة المحتوى · MSI إجهاد مائيّ — (D2b) يغذّيان تأكيد الإجهاد الطيفيّ.
DEFAULT_INDICATORS = ["ndvi", "ndre", "ndsi", "ndmi", "msi"]


@dataclass
class TrackedField:
    field_id: str
    bbox: list[float]  # [west, south, east, north]
    tenant_id: str | None = None  # لتمرير الهويّة لـraster /process
    last_image_id: str | None = None
    last_image_date: str | None = None
    last_checked_at: str | None = None
    last_indicator_job: str | None = None
    last_ndvi_mean: float | None = None  # Stage D: آخر متوسّط NDVI محسوب (Sentinel)
    last_ndvi_date: str | None = None  # تاريخ صورة آخر NDVI ("YYYY-MM-DD")
    last_ndmi_mean: float | None = None  # D2b: آخر متوسّط NDMI (رطوبة المحتوى)
    last_ndmi_date: str | None = None  # تاريخ صورة آخر NDMI
    last_msi_mean: float | None = None  # D2b: آخر متوسّط MSI (إجهاد مائيّ)
    last_msi_date: str | None = None  # تاريخ صورة آخر MSI
    new_images_found: int = 0
    check_errors: int = 0

    def to_dict(self) -> dict:
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


def _parse_capture_time(value: str | None) -> datetime | None:
    """يحلّل وقت التقاط STAC (``last_image_date``) إلى datetime واعٍ بالمنطقة الزمنيّة.

    يقبل ISO8601 كامل (``2026-07-25T10:30:00Z``) أو تاريخاً وحده (``2026-07-25``).
    يُعيد ``None`` إن غاب أو تعذّر التحليل (فيُفحَص الحقل بدل تخطّيه — لا نُسكِت خطأ
    التحليل بتخطٍّ صامت). التاريخ الخام يُثبَّت على منتصف الليل UTC، والقيمة بلا منطقة
    زمنيّة تُعامَل UTC كي تبقى المقارنة مع ``datetime.now(UTC)`` سليمة (لا date↔datetime).
    """
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


class ImageryAutomation:
    """يتابع حقولاً، يكتشف صوراً جديدة، يُطلق حساب المؤشّرات.

    التخزين: بالذاكرة افتراضيّاً، مع استمرار اختياري للقاعدة (set_pool +
    load_from_db) — لو توفّر pool. بلا pool يعمل بالذاكرة (صدق).
    """

    def __init__(self) -> None:
        self._fields: dict[str, TrackedField] = {}
        self._pool = None
        # عدّادات انتظار الدفعة — الانتظار الذي لا يُقاس يعود صمتاً بشكل آخر
        # (SPECTRAL-COLLECTOR-ASYNC-RACE-01). ثلاث حالات مفصولة عمداً:
        #   terminal  = بلغت الدفعة حالة نهائيّة فقُرِئت النتيجة (المسار المقصود)
        #   timed_out = المهمّة معروفة ولم تكتمل ضمن الميزانيّة (بطء/تشبّع)
        #   unknown   = raster-service لا يعرف المهمّة أصلاً (404) — عطل مختلف تماماً،
        #               غالباً حالة مهامّ بالذاكرة موزَّعة على أكثر من نسخة.
        self._batch_waits_terminal = 0
        self._batch_waits_timed_out = 0
        self._batch_waits_unknown = 0

    def set_pool(self, pool) -> None:
        """يربط pool القاعدة لتمكين الاستمرار الدائم."""
        self._pool = pool

    async def _set_tenant_context_if_any(self, conn, tenant_id: str | None) -> None:
        """Set RLS tenant context for writes to tenant-scoped automation rows.

        The automation worker uses a raw asyncpg pool rather than tenant_connection().
        Under FORCE RLS, INSERT/UPDATE to imagery_automation_fields must run with
        app.current_tenant set to the row tenant, otherwise PostgreSQL correctly
        rejects the write. This helper keeps the worker fail-closed without using
        BYPASSRLS.
        """
        if tenant_id:
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant_id))

    async def load_from_db(self) -> int:
        """يحمّل الحقول المتابَعة + آخر صورة معروفة من القاعدة عند الإقلاع.

        صدق: لو لا pool، لا يفعل شيئاً ويُرجع 0. هذا يمنع إعادة معالجة صور
        سبق أن عُولجت بعد إعادة تشغيل المنصّة.

        عابر للمستأجِرين بالتصميم: مجدوِل خلفيّ يفحص الصور لكلّ الحقول المتابَعة
        عبر المستأجِرين، فلا يُضبط app.current_tenant على هذه الاتّصالات الخام
        قصداً. تحت الدور المُقيَّد (NOBYPASSRLS/FORCE RLS) تحتاج هذه المسارات
        دوراً خدميّاً مخصّصاً (BYPASSRLS) — متابعة نشر، لا تغيير سلوك.
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
                        bbox=[r["bbox_west"], r["bbox_south"], r["bbox_east"], r["bbox_north"]],
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
                async with conn.transaction():
                    await self._set_tenant_context_if_any(conn, tf.tenant_id)
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
                        tf.field_id,
                        tf.tenant_id,
                        tf.bbox[0],
                        tf.bbox[1],
                        tf.bbox[2],
                        tf.bbox[3],
                        tf.last_image_id,
                        tf.last_image_date,
                        tf.last_indicator_job,
                        tf.new_images_found,
                        tf.check_errors,
                    )
        except Exception as e:  # noqa: BLE001
            logger.warning("فشل حفظ حقل الصور %s: %s", tf.field_id, e)

    def register_field(
        self, field_id: str, bbox: list[float], tenant_id: str | None = None
    ) -> None:
        """يسجّل حقلاً للمتابعة (بالذاكرة فوراً). bbox = [west,south,east,north]."""
        if len(bbox) != 4:
            raise ValueError("bbox يجب أن يكون [west, south, east, north]")
        if field_id in self._fields:
            self._fields[field_id].bbox = bbox
            if tenant_id:
                self._fields[field_id].tenant_id = tenant_id
        else:
            self._fields[field_id] = TrackedField(field_id=field_id, bbox=bbox, tenant_id=tenant_id)

    async def register_field_persistent(
        self, field_id: str, bbox: list[float], tenant_id: str | None = None
    ) -> None:
        """يسجّل + يحفظ في القاعدة (لو توفّر pool)."""
        self.register_field(field_id, bbox, tenant_id)
        await self._persist_field(self._fields[field_id])

    def unregister_field(self, field_id: str) -> bool:
        return self._fields.pop(field_id, None) is not None

    def tracked_count(self) -> int:
        return len(self._fields)

    def status(self) -> dict:
        return {
            "tracked_fields": len(self._fields),
            "raster_service_url": raster_service_url(),
            "auto_indicators": DEFAULT_INDICATORS,
            # المزوّد الافتراضيّ CDSE (إن هُيّئ في raster-service) مع fallback إلى Element84.
            "default_provider": "cdse",
            "fallback_provider": "element84",
            # قابليّة قراءة السباق المُصلَح: بلا هذه الأرقام يعود «لم تُكتَب القيم» غير
            # مرئيّ من الخارج تماماً كما كان قبل الإصلاح.
            "batch_waits": {
                "terminal": self._batch_waits_terminal,
                "timed_out": self._batch_waits_timed_out,
                "unknown": self._batch_waits_unknown,
                "budget_s": _batch_wait_budget_s(),
                "poll_interval_s": _batch_poll_interval_s(),
            },
            "fields": [f.to_dict() for f in self._fields.values()],
        }

    @staticmethod
    def _bbox_from_guard_bbox(bbox: dict) -> list[float]:
        """Convert SAHOOL guard bbox dict to STAC bbox [west,south,east,north]."""
        return [
            float(bbox["min_lng"]),
            float(bbox["min_lat"]),
            float(bbox["max_lng"]),
            float(bbox["max_lat"]),
        ]

    @staticmethod
    def _scene_id(scene: dict) -> str | None:
        return scene.get("item_id") or scene.get("id") or scene.get("image_id")

    @staticmethod
    def _band_hrefs_from_scene(scene: dict) -> dict[str, str]:
        """Normalize raster-service /v1/imagery/best STAC asset names to process-from-stac names.

        Element84 returns `bands_urls` with Sentinel-2 asset keys such as rededge1,
        swir16 and swir22. raster-service/stac_vrt expects canonical names:
        red/nir/green/blue/swir1/swir2/rededge/scl. We only pass existing links;
        missing bands make the raster service fail honestly instead of inventing data.
        """
        bands = scene.get("bands_urls") or scene.get("band_urls") or scene.get("assets") or {}

        def pick(*keys: str) -> str | None:
            for k in keys:
                v = bands.get(k)
                if isinstance(v, dict):
                    v = v.get("href")
                if v:
                    return str(v)
            return None

        out = {
            "red": pick("red", "B04"),
            "nir": pick("nir", "nir08", "B08", "B8A"),
            "green": pick("green", "B03"),
            "blue": pick("blue", "B02"),
            "rededge": pick("rededge", "rededge1", "rededge2", "rededge3", "B05", "B06", "B07"),
            "swir1": pick("swir1", "swir16", "B11"),
            "swir2": pick("swir2", "swir22", "B12"),
            "scl": pick("scl", "SCL"),
        }
        return {k: v for k, v in out.items() if v}

    async def _try_cdse(
        self,
        *,
        field_id: str,
        tenant_id: str,
        bbox: list[float],
        geometry: dict | None,
        inds: list[str],
        lookback_days: int,
        max_cloud_pct: float,
        reason: str,
        tf,
        date_from: str | None = None,
        date_to: str | None = None,
        geometry_revision: int | None = None,
    ) -> dict | None:
        """Try CDSE (the default, stronger provider) first; return None to fall back to Element84.

        Honest semantics: CDSE not configured (``available:false``) or any transport/processing
        error ⇒ return None ⇒ caller silently uses the existing Element84 STAC path. We only
        return a result dict when CDSE actually queued processing — never fabricate data.
        """
        try:
            body = (
                await process_field_cdse(
                    field_id,
                    tenant_id=tenant_id,
                    payload={
                        "tenant_id": tenant_id,
                        "indicators": inds,
                        "bbox": bbox,
                        "geometry": geometry,
                        "lookback_days": lookback_days,
                        "max_cloud_pct": max_cloud_pct,
                        "geometry_revision": geometry_revision,  # v143: نَسَب هندسة الحقل
                        **(
                            {"date_from": date_from, "date_to": date_to or date_from}
                            if date_from or date_to
                            else {}
                        ),
                    },
                )
                or {}
            )
        except Exception:  # noqa: BLE001 — CDSE متعذّر ⇒ fallback صامت إلى Element84
            return None
        # CDSE غير مُهيّأ (لا اعتمادات) ⇒ المسار القائم (Element84) دون ضجيج.
        if not body.get("available"):
            return None
        if not body.get("queued"):
            return None
        tf.new_images_found += 1
        tf.last_indicator_job = body.get("job_id")
        await self._persist_field(tf)
        return {
            "status": "queued",
            "queued": True,
            "provider": "cdse",
            "field_id": field_id,
            "reason": reason,
            "job_id": body.get("job_id"),
            "indicators": body.get("indicators", inds),
            "real_data": False,
            "note_ar": (
                "أُطلقت معالجة CDSE (Sentinel-2 الافتراضيّ الأقوى). real_data=true فقط بعد "
                "اكتمال COG وقراءته. fallback إلى Element84 يحدث تلقائيّاً عند تعذّر CDSE."
            ),
        }

    async def trigger_field_imagery_processing(
        self,
        *,
        field_id: str,
        tenant_id: str,
        bbox: list[float] | dict,
        geometry: dict | None = None,
        reason: str = "manual.refresh",
        lookback_days: int = 30,
        max_cloud_pct: float = 40.0,
        indicators: list[str] | None = None,
        date: str | None = None,
        geometry_revision: int | None = None,
    ) -> dict:
        """Find the best real Sentinel-2 STAC scene and launch raster processing.

        This is the real-data activation bridge. It does not synthesize values:
        - no STAC scene => no job, honest `queued:false`;
        - missing band hrefs => no job, honest `queued:false`;
        - raster-service error => propagated in `status:error` for UI/operator visibility.
        """
        if isinstance(bbox, dict):
            stac_bbox = self._bbox_from_guard_bbox(bbox)
        else:
            stac_bbox = [float(x) for x in bbox]
        if len(stac_bbox) != 4:
            raise ValueError("bbox must be [west,south,east,north]")
        inds = indicators or DEFAULT_INDICATORS
        # Ensure the field is tracked by the scheduler as well as processed once now.
        self.register_field(field_id, stac_bbox, tenant_id=tenant_id)
        tf = self._fields[field_id]

        # ── المزوّد الافتراضيّ: CDSE (أقوى) ───────────────────────────────
        # نجرّب CDSE أوّلاً (يحسب المؤشّر خادميّاً على نطاقات Sentinel-2 الكاملة).
        # غير مُهيّأ / متعذّر ⇒ None ⇒ نسقط بصمت إلى Element84 أدناه (لا كسر، لا تلفيق).
        cdse = await self._try_cdse(
            field_id=field_id,
            tenant_id=tenant_id,
            bbox=stac_bbox,
            geometry=geometry,
            inds=inds,
            lookback_days=lookback_days,
            max_cloud_pct=max_cloud_pct,
            reason=reason,
            tf=tf,
            date_from=f"{date[:10]}T00:00:00Z" if date else None,
            date_to=f"{date[:10]}T23:59:59Z" if date else None,
            geometry_revision=geometry_revision,
        )
        if cdse is not None:
            return cdse
        try:
            best_body = await get_best_imagery_scene(
                bbox=stac_bbox,
                lookback_days=lookback_days,
                max_cloud_pct=max_cloud_pct,
            )
        except Exception as e:  # noqa: BLE001
            tf.check_errors += 1
            await self._persist_field(tf)
            return {
                "status": "error",
                "queued": False,
                "field_id": field_id,
                "reason": reason,
                "error": type(e).__name__,
                "note_ar": "تعذّر البحث عن مشهد Sentinel-2 حقيقي عبر raster-service.",
            }

        scene = best_body.get("best")
        if not scene:
            await self._persist_field(tf)
            return {
                "status": "no_scene",
                "queued": False,
                "field_id": field_id,
                "reason": reason,
                "candidates": best_body.get("candidates", 0),
                "note_ar": best_body.get("note") or "لا يوجد مشهد Sentinel-2 مطابق ضمن المعايير.",
            }

        band_hrefs = self._band_hrefs_from_scene(scene)
        required = {"red", "nir"}
        if not required.issubset(band_hrefs):
            await self._persist_field(tf)
            return {
                "status": "missing_bands",
                "queued": False,
                "field_id": field_id,
                "reason": reason,
                "scene_id": self._scene_id(scene),
                "available_bands": sorted(band_hrefs),
                "note_ar": "المشهد لا يحتوي على نطاقات كافية لحساب NDVI الحقيقي.",
            }

        jobs: list[dict] = []
        failures: list[dict] = []
        for indicator in inds:
            try:
                body = await process_field_from_stac(
                    field_id,
                    tenant_id=tenant_id,
                    payload={
                        "tenant_id": tenant_id,
                        "indicator": indicator,
                        "band_hrefs": band_hrefs,
                        "scene_id": self._scene_id(scene),
                        "capture_datetime": scene.get("datetime") or scene.get("date"),
                        "apply_cloud_mask": True,
                        "clip_polygon_geojson": geometry,
                        "source_format": "sentinel2_l2a",
                        "geometry_revision": geometry_revision,  # v143: نَسَب هندسة الحقل
                    },
                )
                jobs.append({"indicator": indicator, **(body or {})})
            except Exception as e:  # noqa: BLE001
                failures.append({"indicator": indicator, "error": type(e).__name__})

        tf.last_image_id = self._scene_id(scene)
        tf.last_image_date = scene.get("datetime") or scene.get("date")
        tf.new_images_found += 1 if jobs else 0
        if jobs:
            tf.last_indicator_job = jobs[0].get("job_id")
        if failures:
            tf.check_errors += len(failures)
        await self._persist_field(tf)
        return {
            "status": "queued" if jobs else "error",
            "queued": bool(jobs),
            "field_id": field_id,
            "reason": reason,
            "scene_id": tf.last_image_id,
            "capture_datetime": tf.last_image_date,
            "jobs": jobs,
            "failures": failures,
            "real_data": False,
            "note_ar": "أُطلقت معالجة COG من Sentinel-2 الحقيقي. تصبح real_data=true فقط بعد اكتمال COG وقراءته.",
        }

    async def scan_all(
        self, lookback_days: int = 10, min_hours_since_last_capture: float = 24.0
    ) -> dict:
        """يفحص كلّ الحقول المتابَعة عن صور جديدة (تُستدعى من scheduler).

        معزول لكلّ حقل. يُرجع ملخّص: كم حقل فُحص، كم تُخطّي، كم صورة جديدة، كم فشل.
        صدق: لو لا حقول → لا يضرب raster-service.

        كادينس لكلّ حقل: لا يُعاد فحص حقل إلّا بعد مرور ``min_hours_since_last_capture``
        (افتراض 24 ساعة) على **وقت التقاط صورته السابقة** (``last_image_date``). حقل بلا
        وقت التقاط معروف (لم تُلتقَط له صورة بعد) يُفحَص دائماً. هذا يجعل المزامنة فعليّاً
        «كلّ 24 ساعة من وقت التقاط الصورة السابقة» لا كنساً أعمى لكلّ حقل كلّ دورة.
        """
        if not self._fields:
            return {
                "scanned": 0,
                "skipped": 0,
                "new_images": 0,
                "failed": 0,
                "note": "لا حقول مُتابَعة",
            }

        now = datetime.now(UTC)
        start = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
        min_gap = timedelta(hours=max(0.0, min_hours_since_last_capture))

        scanned = 0
        skipped = 0
        new_images = 0
        failed = 0
        errors: list[str] = []

        for field_id, tf in list(self._fields.items()):
            # حارس per-field: تخطَّ الحقل إن لم تمرّ 24 ساعة على وقت التقاط صورته
            # السابقة (لا وقت التقاط ⇒ يُفحَص). لا يُعدّ فحصاً ولا يضرب raster-service.
            last_capture = _parse_capture_time(tf.last_image_date)
            if last_capture is not None and (now - last_capture) < min_gap:
                skipped += 1
                continue
            scanned += 1
            tf.last_checked_at = now.isoformat()
            try:
                # ابحث عن صور Sentinel-2 جديدة لهذا الحقل
                body = await search_imagery_scenes(
                    bbox=tf.bbox,
                    datetime_start=start,
                    datetime_end=end,
                    limit=5,
                )
                items = body.get("items", [])
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
                    await self._trigger_indicators(tf, newest)
                    # احفظ الحالة الجديدة (لا إعادة معالجة بعد إعادة التشغيل)
                    await self._persist_field(tf)
            except Exception as e:  # noqa: BLE001 — عزل لكلّ حقل
                failed += 1
                tf.check_errors += 1
                errors.append(f"{field_id}: {type(e).__name__}")
                logger.warning("فشل فحص صور الحقل %s: %s", field_id, e)

        return {
            "scanned": scanned,
            "skipped": skipped,
            "new_images": new_images,
            "failed": failed,
            "errors": errors[:10],
        }

    async def _trigger_indicators(self, tf: TrackedField, image: dict) -> None:
        """يطلب حساب المؤشّرات لصورة جديدة عبر raster-service /v1/process/batch.

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
                "bands": {
                    "red": 1,
                    "green": 2,
                    "blue": 3,
                    "nir": 4,
                    "rededge": 5,
                    "swir1": 6,
                    "swir2": 7,
                },
                "scene_id": image.get("id") or image.get("image_id"),
                "capture_datetime": image.get("datetime") or image.get("date"),
            }
            body = await process_indicator_batch(
                tenant_id=tf.tenant_id,
                payload=payload,
            )
            tf.last_indicator_job = body.get("job_id")
            # `/v1/process/batch` **غير متزامن**: يُرجِع `pending` فور جدولة المهمّة
            # الخلفيّة، والمهامّ الفرعيّة `{job_id}_{indicator}` تُنشَأ **داخلها**. القراءة
            # الفوريّة كانت تصطدم بـ404 دائماً فلا تُكتَب أيّ قيمة طيفيّة
            # (SPECTRAL-COLLECTOR-ASYNC-RACE-01). ننتظر حالة نهائيّة **مرّةً واحدة**
            # للدفعة، لا مرّةً لكلّ مؤشّر.
            if not await self._await_batch_terminal(tf, body):
                return
            # Stage D: best-effort — استخرج متوسّط NDVI الحقيقيّ واحفظه (fail-safe).
            await self._collect_ndvi_value(tf, image, body)
            # D2b: best-effort — استخرج NDMI/MSI (تأكيد الإجهاد الطيفيّ) واحفظهما.
            await self._collect_spectral_values(tf, image, body)
        except Exception as e:  # noqa: BLE001
            logger.warning("فشل طلب مؤشّرات الحقل %s: %s", tf.field_id, e)

    async def _await_batch_terminal(self, tf: TrackedField, batch_body: dict) -> bool:
        """ينتظر بلوغ دفعة المؤشّرات حالةً نهائيّة قبل قراءة نتائجها الفرعيّة.

        يُرجِع ``True`` حين يصحّ الشروع في القراءة، و``False`` حين لا يصحّ — وعندئذٍ
        **لا تُقرأ** النتائج أصلاً: نداء يعرف سلفاً أنّه سيصطدم بـ404 ليس «أفضل جهد»
        بل ضجيج يُخفي السبب.

        ثلاث نهايات مفصولة لأنّها ثلاثة أعطال مختلفة العلاج:

        * **نهائيّة** ⇒ ``True``. حتّى ``failed`` تُقرأ: قد تنجح مؤشّرات وتفشل أخرى،
          والمهمّة الفرعيّة الناجحة نتيجتها صالحة.
        * **نفاد الميزانيّة** والمهمّة ما تزال قيد التنفيذ ⇒ ``False`` + ``warning``
          + عدّاد. القيمة تُترَك ``NULL`` ولا تُختلَق، والدورة التالية تُعيد المحاولة.
        * **مهمّة مجهولة (404)** ⇒ ``False`` فوراً بلا انتظار + عدّاد منفصل. الانتظار
          هنا عبث: الحالة بالذاكرة قد تكون على نسخة أخرى من raster-service، والزمن
          لن يُصلح ذلك. خلطها بالمهلة كان سيُخفي عطل نشر خلف «بطء».

        ميزانيّة صفر تُعطّل الانتظار وتُعيد السلوك السابق حرفيّاً — بوّابة تراجع
        تشغيليّة، وهي أيضاً ما يجعل تكذيب هذا الإصلاح ممكناً في اختبار.
        """
        job_id = batch_body.get("job_id") or tf.last_indicator_job
        if not job_id:
            return False
        status = str(batch_body.get("status") or "")
        if status in _BATCH_TERMINAL_STATUSES:
            # مسار إلغاء التكرار: الدفعة مكتملة سلفاً وأُعيد job_id السلطويّ نفسه.
            self._batch_waits_terminal += 1
            return True
        budget = _batch_wait_budget_s()
        if budget <= 0:
            return True
        interval = _batch_poll_interval_s()
        deadline = datetime.now(UTC) + timedelta(seconds=budget)
        last_seen = status or "pending"
        while True:
            body = await get_job_status(job_id, tenant_id=tf.tenant_id)
            if body is None:
                self._batch_waits_unknown += 1
                logger.warning(
                    "دفعة مؤشّرات مجهولة لدى raster-service (%s/%s) — لا قراءة ولا انتظار",
                    tf.field_id,
                    job_id,
                )
                return False
            last_seen = str(body.get("status") or last_seen)
            if last_seen in _BATCH_TERMINAL_STATUSES:
                self._batch_waits_terminal += 1
                return True
            if datetime.now(UTC) >= deadline:
                self._batch_waits_timed_out += 1
                logger.warning(
                    "دفعة مؤشّرات لم تكتمل خلال %.0fث (%s/%s، آخر حالة: %s) — "
                    "تُترَك القيم NULL وتُعاد المحاولة في الدورة التالية",
                    budget,
                    tf.field_id,
                    job_id,
                    last_seen,
                )
                return False
            await asyncio.sleep(interval)

    async def _fetch_index_mean(
        self, job_id: str, indicator: str, tenant_id: str | None = None
    ) -> float | None:
        """best-effort: متوسّط مؤشّر من المهمّة الفرعيّة «{job_id}_{indicator}».

        raster-service: /v1/process/batch ينشئ مهمّة فرعيّة لكلّ مؤشّر بمعرّف
        «{batch_job_id}_{indicator}»، ونتيجتها GET /v1/jobs/{id}/result بشكل
        {stats:{mean, valid_pixels, ...}}. صدق: نُرجِع المتوسّط فقط حين valid_pixels>0
        (وإلّا 0.0 افتراضيّ بلا معنى). fail-safe تامّ: أيّ تعذّر ⇒ None (لا تلفيق).

        **409 يُترجَم None لا استثناءً:** الدفعة تبلغ حالةً نهائيّة وقد يفشل فيها مؤشّر
        واحد، فتبقى مهمّته الفرعيّة غير مكتملة ويردّ `/result` بـ409. تركُ الاستثناء
        ينتشر كان يُسقِط **بقيّة** المؤشّرات في المستدعي نفسه (`_collect_spectral_values`
        يقرأ NDMI ثمّ MSI بالتتابع)، فيضيع مؤشّر ناجح بسبب آخر فاشل. المؤشّر غير المكتمل
        ليس عطلاً في القراءة، بل **غياب قيمة** — وهذا تعريف None هنا.
        """
        from fastapi import HTTPException

        try:
            body = await get_job_result(f"{job_id}_{indicator}", tenant_id=tenant_id)
        except HTTPException as exc:
            if exc.status_code == 409:
                logger.debug(
                    "مهمّة فرعيّة غير مكتملة (%s_%s): %s — لا قيمة",
                    job_id,
                    indicator,
                    exc.detail,
                )
                return None
            raise
        if not body:
            return None
        stats = (body or {}).get("stats") or {}
        mean = stats.get("mean")
        valid = stats.get("valid_pixels")
        if mean is None or not valid:  # لا قيمة أو لا بكسلات صالحة ⇒ None
            return None
        return float(mean)

    @staticmethod
    def _image_date(image: dict) -> str | None:
        return (image.get("datetime") or image.get("date") or "")[:10] or None

    async def _collect_ndvi_value(self, tf: TrackedField, image: dict, batch_body: dict) -> None:
        """best-effort: يستخرج متوسّط NDVI الحقيقيّ من نتيجة المعالجة ويحفظه.

        fail-safe تامّ: أيّ تعذّر ⇒ تخطٍّ صامت، العمود يبقى NULL (لا تلفيق).
        """
        try:
            job_id = batch_body.get("job_id") or tf.last_indicator_job
            if not job_id:
                return
            mean = await self._fetch_index_mean(job_id, "ndvi", tenant_id=tf.tenant_id)
            if mean is None:
                return
            tf.last_ndvi_mean = mean
            tf.last_ndvi_date = self._image_date(image)
            await self._persist_ndvi(tf)
        except Exception as e:  # noqa: BLE001 — best-effort، لا يكسر الأتمتة أبداً
            logger.debug("جمع قيمة NDVI تخطٍّ للحقل %s: %s", tf.field_id, e)

    async def _collect_spectral_values(
        self, tf: TrackedField, image: dict, batch_body: dict
    ) -> None:
        """best-effort (D2b): يستخرج NDMI/MSI ويحفظهما — تأكيد الإجهاد الطيفيّ.

        كلّ مؤشّر مستقلّ: المتوفّر يُحفَظ والغائب يبقى NULL (صدق — لا تلفيق). fail-safe
        تامّ: أيّ تعذّر ⇒ تخطٍّ صامت لا يكسر الأتمتة.
        """
        try:
            job_id = batch_body.get("job_id") or tf.last_indicator_job
            if not job_id:
                return
            img_date = self._image_date(image)
            ndmi = await self._fetch_index_mean(job_id, "ndmi", tenant_id=tf.tenant_id)
            if ndmi is not None:
                tf.last_ndmi_mean = ndmi
                tf.last_ndmi_date = img_date
            msi = await self._fetch_index_mean(job_id, "msi", tenant_id=tf.tenant_id)
            if msi is not None:
                tf.last_msi_mean = msi
                tf.last_msi_date = img_date
            if ndmi is not None or msi is not None:
                await self._persist_spectral(tf)
        except Exception as e:  # noqa: BLE001 — best-effort، لا يكسر الأتمتة أبداً
            logger.debug("جمع NDMI/MSI تخطٍّ للحقل %s: %s", tf.field_id, e)

    async def _persist_ndvi(self, tf: TrackedField) -> None:
        """يحفظ متوسّط NDVI + تاريخه في imagery_automation_fields (fail-safe)."""
        if self._pool is None:
            return
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    await self._set_tenant_context_if_any(conn, tf.tenant_id)
                    await conn.execute(
                        "UPDATE imagery_automation_fields "
                        "SET last_ndvi_mean = $2, last_ndvi_date = $3::date WHERE field_id = $1",
                        tf.field_id,
                        tf.last_ndvi_mean,
                        tf.last_ndvi_date,
                    )
        except Exception as e:  # noqa: BLE001 — حفظ best-effort
            logger.debug("حفظ NDVI تخطٍّ للحقل %s: %s", tf.field_id, e)

    async def _persist_spectral(self, tf: TrackedField) -> None:
        """يحفظ NDMI/MSI + تاريخيهما في imagery_automation_fields (fail-safe، D2b).

        COALESCE يُبقي القيمة المخزَّنة حين يكون المؤشّر الحاليّ None (لا يمحو قراءة
        سابقة بمؤشّر مفقود في صورة لاحقة).
        """
        if self._pool is None:
            return
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    await self._set_tenant_context_if_any(conn, tf.tenant_id)
                    await conn.execute(
                        "UPDATE imagery_automation_fields SET "
                        "last_ndmi_mean = COALESCE($2, last_ndmi_mean), "
                        "last_ndmi_date = COALESCE($3::date, last_ndmi_date), "
                        "last_msi_mean = COALESCE($4, last_msi_mean), "
                        "last_msi_date = COALESCE($5::date, last_msi_date) "
                        "WHERE field_id = $1",
                        tf.field_id,
                        tf.last_ndmi_mean,
                        tf.last_ndmi_date,
                        tf.last_msi_mean,
                        tf.last_msi_date,
                    )
        except Exception as e:  # noqa: BLE001 — حفظ best-effort
            logger.debug("حفظ NDMI/MSI تخطٍّ للحقل %s: %s", tf.field_id, e)


# مثيل وحيد للتطبيق
imagery_automation = ImageryAutomation()
