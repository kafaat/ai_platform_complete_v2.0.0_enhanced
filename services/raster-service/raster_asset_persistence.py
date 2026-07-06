"""Best-effort persistence adapter for processed raster assets.

Extracted from ``main.py`` to keep FastAPI route wiring separate from database
persistence details. The public functions intentionally mirror the old private
names so ``main.py`` can re-export them for existing tests/routers.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

logger = logging.getLogger("raster-service")

# معرّف الحقل القانونيّ نصّيّ (fld_<hex>) والعمود raster_assets.field_id هو
# VARCHAR(50) لا UUID — فرضُ UUID عليه أسقط الحفظ لكلّ حقل حقيقيّ بصمت
# (بلاغ 2026-07-04). tenant_id يبقى UUID (عموده UUID فعلاً — قصد تصليب 06-26).
_FIELD_ID_TEXT_RE = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


def _is_valid_uuid_text(value: str | None) -> bool:
    if not value or not str(value).strip():
        return False
    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False


def _is_valid_field_id_text(value: str | None) -> bool:
    """معرّف حقل آمن لعمود VARCHAR(50): fld_* أو UUID — لا فارغ/محارف غريبة."""
    return bool(value) and bool(_FIELD_ID_TEXT_RE.fullmatch(str(value).strip()))


def persist_raster_asset(
    req: Any,
    cog_url: str,
    meta: dict,
    bounds: list,
    stats: dict,
    job_id: str | None = None,
) -> bool:
    """يُدرج صفّاً في raster_assets (best-effort). يُرجِع True عند الحفظ الفعليّ.

    _run_processing يعمل في threadpool (مهمّة خلفيّة متزامنة) فلا حلقة
    أحداث في خيطه؛ لذا asyncio.run آمن هنا. غياب القاعدة (لا DATABASE_URL/
    لا جدول/لا شبكة) يُبتلع بصدق ولا يُفشل المعالجة (يُرجِع False).
    """
    if not _is_valid_field_id_text(req.field_id):
        logger.warning("raster_assets persist skipped: missing/invalid field_id=%r", req.field_id)
        return False
    if (
        req.tenant_id is not None
        and str(req.tenant_id).strip()
        and not _is_valid_uuid_text(req.tenant_id)
    ):
        logger.warning("raster_assets persist skipped: invalid tenant_id=%r", req.tenant_id)
        return False
    try:
        import asyncio

        import db_persist
        import quality_metrics

        # v131 (v62.3-B): مقاييس جودة الصور من عدّادات البكسلات في stats.
        # valid_pixels/nodata_pixels يوفّرها _process_pixels/_process_precomputed_pixels؛
        # غيابهما (بنية بلا rasterio) ⇒ إجماليّ = 0 ⇒ نسب None (لا اختراع).
        _vp = stats.get("valid_pixels")
        _np = stats.get("nodata_pixels")
        _total = (int(_vp) + int(_np)) if (_vp is not None and _np is not None) else None
        _quality = quality_metrics.compute_quality_metrics(
            valid_pixels=int(_vp) if _vp is not None else None,
            total_pixels=_total,
            cloud_pct=stats.get("cloud_pct"),
        )

        # footprint كـbbox polygon بـ4326 (الحدود معاد إسقاطها)
        minlon, minlat, maxlon, maxlat = bounds[0], bounds[1], bounds[2], bounds[3]
        footprint = {
            "type": "Polygon",
            "coordinates": [
                [
                    [minlon, minlat],
                    [maxlon, minlat],
                    [maxlon, maxlat],
                    [minlon, maxlat],
                    [minlon, minlat],
                ]
            ],
        }

        async def _do():
            ok = await db_persist.insert_raster_asset(
                field_id=req.field_id,
                tenant_id=req.tenant_id,
                scene_id=req.scene_id,
                acquisition_date=req.capture_datetime,
                satellite=req.source_format.value,
                index_name=req.indicator.value,
                cloud_pct=stats.get("cloud_pct"),
                srid=meta.get("srid"),
                cog_uri=cog_url,
                bands=req.bands.model_dump() if hasattr(req.bands, "model_dump") else None,
                nodata=meta.get("nodata"),
                footprint=footprint,
                valid_pixel_ratio=_quality["valid_pixel_ratio"],
                coverage_ratio=_quality["coverage_ratio"],
                index_quality_flags=_quality["index_quality_flags"],
                processing_job_id=job_id,  # v142: تتبّع + يُغني layer_owner_tenant عن ILIKE
                # v105 (v4-audit): أعمدة الجودة تُكتب الآن فعلاً كي يعمل الترتيب الواعي بالجودة.
                # confidence هو الدرجة 0..1 (أعلى=أفضل)؛ cloud_pct محسوب على AOI المقصوص.
                quality_score=stats.get("confidence"),
                aoi_cloud_pct=stats.get("cloud_pct"),
                cloud_mask_sources=stats.get("cloud_mask_sources"),
                # v143 (FINDING-004): مراجعة الهندسة السارية وقت المعالجة (None إن لم تُمرَّر).
                geometry_revision=getattr(req, "geometry_revision", None),
                provenance={
                    "stats": {
                        k: stats.get(k)
                        for k in (
                            "min",
                            "max",
                            "mean",
                            "std",
                            "cloud_pct",
                            "cloud_mask_applied",
                            "cloud_mask_sources",  # v4-audit: كان يُنتَج ويُسقَط من النَّسَب
                            "quality",
                            "confidence",
                        )
                    },
                    # v143: النَّسَب — مراجعة الهندسة في الأصل نفسه (فوق العمود المخصّص).
                    "geometry_revision": getattr(req, "geometry_revision", None),
                },
            )
            # FINDING-008: جسر الكتالوج — عند نجاح الأصل نكتب صفّاً مُقابِلاً في
            # raster_registry (كان يملؤه فقط مسار REST يدويّ) كي لا يبقى الكتالوج فارغاً.
            if ok and cog_url and not str(cog_url).startswith("file://"):
                await db_persist.insert_raster_registry_entry(
                    tenant_id=req.tenant_id,
                    field_id=req.field_id,
                    scene_id=req.scene_id,
                    product_date=req.capture_datetime,
                    index_type=req.indicator.value,
                    cog_url=cog_url,
                    cloud_pct=stats.get("cloud_pct"),
                    quality_score=stats.get("confidence"),
                    resolution_m=meta.get("resolution_m") or 10.0,
                    bbox=list(bounds) if bounds else None,
                    bands=req.bands.model_dump() if hasattr(req.bands, "model_dump") else None,
                    metadata={
                        "quality": stats.get("quality"),
                        "confidence": stats.get("confidence"),
                        "provider": getattr(req, "provider", None),
                        "geometry_revision": getattr(req, "geometry_revision", None),
                    },
                )
            return ok

        # v5-audit F1: نلتقط نتيجة الحفظ ونُصدِر سطراً منظَّماً — «job completed» وحده
        # كان لا يُميّز «حُفِظ في DB» عن «في الذاكرة فقط والإدراج عاد False بصمت»، فبعد
        # إعادة التشغيل قد يفشل الترطيب رغم «completed». الآن persisted صريح في السجلّ والمهمّة.
        _holder = {"ok": False}
        try:
            _holder["ok"] = bool(asyncio.run(_do()))
        except RuntimeError:
            # حلقة أحداث قائمة بالفعل (نادر هنا) — شغّلها في خيط مستقلّ
            import threading

            def _runner():
                _holder["ok"] = bool(asyncio.run(_do()))

            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            # v9-F2: مهلة أوسع (60s) لإدراج DB البطيء. لو تجاوزها الخيط لا نُعلن
            # persisted=false كذباً بل نُصرّح بأنّ النتيجة «غير حاسمة» (قد يكتمل لاحقاً).
            t.join(timeout=60)
            if t.is_alive():
                logger.warning(
                    "raster_assets persist result indeterminate field_id=%s index=%s "
                    "(خيط الإدراج ما زال يعمل بعد 60s — قد يكتمل الحفظ خلفيّاً)",
                    req.field_id,
                    req.indicator.value,
                )
        if _holder["ok"]:
            logger.info(
                "raster_assets persist ok field_id=%s tenant_id=%s index=%s scene_id=%s "
                "acquisition_date=%s cog_uri=%s",
                req.field_id,
                req.tenant_id,
                req.indicator.value,
                req.scene_id,
                req.capture_datetime,
                cog_url,
            )
        else:
            logger.warning(
                "raster_assets persist failed field_id=%s index=%s scene_id=%s "
                "(best-effort؛ COG في الذاكرة/القرص المحلّيّ فقط — قد يفشل الترطيب بعد إعادة التشغيل)",
                req.field_id,
                req.indicator.value,
                req.scene_id,
            )
        return _holder["ok"]
    except Exception as _dbe:  # noqa: BLE001 — صدق: لا نُفشل المعالجة لغياب القاعدة
        logger.warning("raster_assets persist skipped: %s", _dbe)
        return False


# Backward-compatible private name for old tests/importers.
_persist_raster_asset = persist_raster_asset
