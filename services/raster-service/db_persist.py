"""
db_persist.py — حفظ أصول الراستر في قاعدة البيانات (best-effort).

يُدرج صفّاً في جدول raster_assets بعد كتابة COG، مع ضبط app.current_tenant
لعزل المستأجر (RLS). كلّ شيء مغلّف في try/except: غياب القاعدة (DATABASE_URL
غير مضبوط أو الجدول غير مُهاجَر بعد) لا يُفشل المعالجة.

⚠ الجدول raster_assets يُضاف بمهاجرة أخرى — نشير إليه، لا ننشئه.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid

logger = logging.getLogger("raster-service.db")

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _parse_quality_flags(raw: object) -> list:
    """Normalize index_quality_flags (jsonb text from asyncpg) to a list.

    asyncpg يعيد jsonb نصّاً (بلا codec مُسجَّل). None/فارغ ⇒ []؛ نصّ غير صالح ⇒ [].
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _valid_uuid_text(value: str | None) -> bool:
    """Validate UUID text before asyncpg binds it to UUID columns."""
    if not value or not str(value).strip():
        return False
    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False


# معرّف الحقل القانونيّ في المنصّة نصّيّ (fld_<hex>) والعمود VARCHAR(50) لا UUID —
# فرضُ UUID عليه (تصليب 2026-06-26 الزائد) كان يُسقط حفظ raster_assets لكلّ حقل
# حقيقيّ بصمت (بلاغ 2026-07-04: «persist skipped: missing/invalid field_id='fld_…'»
# رغم نجاح المعالجة). نقبل محارف آمنة فقط وبطول العمود — UUID يطابق أيضاً.
_FIELD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


def _valid_field_id_text(value: str | None) -> bool:
    """معرّف حقل نصّيّ آمن لعمود VARCHAR(50) (fld_* أو UUID) — لا فارغ/محارف غريبة."""
    return bool(value) and bool(_FIELD_ID_RE.fullmatch(str(value).strip()))


async def _connect():
    """يفتح اتّصالاً جديداً لكلّ عمليّة (لا pool مُخزَّن).

    FIX: تخزين pool واحد يكسر عبر حلقات الحدث — الإدراج يجري في حلقة
    asyncio.run الخاصّة بمهمّة الخلفية، والقراءة في حلقة الخادم؛ مشاركة pool
    مُقيَّد بحلقة ميّتة ⇒ 'another operation is in progress'. اتّصال قصير العمر
    لكلّ عمليّة (نادرة: الإدراج مرّة لكلّ معالجة، والقراءة مرّة لكلّ حقل بعد
    إعادة التشغيل) يتجنّب ذلك تماماً.
    """
    if not DATABASE_URL:
        return None
    try:
        import asyncpg
    except ImportError:
        return None
    try:
        return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as e:  # noqa: BLE001 — غياب القاعدة لا يُفشل المعالجة
        logger.warning("raster_assets connect unavailable: %s", e)
        return None


async def insert_raster_asset(
    *,
    field_id: str | None,
    tenant_id: str | None,
    scene_id: str | None,
    acquisition_date: str | None,
    satellite: str | None,
    index_name: str,
    cloud_pct: float | None,
    srid: int | None,
    cog_uri: str,
    bands: dict | list | None,
    nodata: float | None,
    footprint: dict | None,
    provenance: dict | None,
    valid_pixel_ratio: float | None = None,
    coverage_ratio: float | None = None,
    index_quality_flags: list | None = None,
    processing_job_id: str | None = None,
    quality_score: float | None = None,
    aoi_cloud_pct: float | None = None,
    cloud_mask_sources: list | None = None,
    geometry_revision: int | None = None,
    asset_status: str = "ready",
    product_identity_key: str | None = None,
    algorithm_version: str | None = None,
    qa_mask_version: str | None = None,
    field_geometry_hash: str | None = None,
) -> bool:
    """يُدرج صفّاً في raster_assets (best-effort). يُرجِع True عند النجاح.

    يضبط app.current_tenant عبر set_config قبل الإدراج (RLS). أيّ خطأ
    (لا قاعدة / لا جدول / لا شبكة) يُبتلع بصدق ويُرجِع False دون رمي.
    """
    if not _valid_field_id_text(field_id):
        logger.warning("raster_assets insert skipped: missing/invalid field_id=%r", field_id)
        return False
    if tenant_id is not None and str(tenant_id).strip() and not _valid_uuid_text(tenant_id):
        logger.warning("raster_assets insert skipped: invalid tenant_id=%r", tenant_id)
        return False

    conn = await _connect()
    if conn is None:
        return False

    footprint_geojson = json.dumps(footprint) if footprint else None
    bands_json = json.dumps(bands) if bands is not None else None
    provenance_json = json.dumps(provenance) if provenance else None
    # v131 (v62.3-B): أعمدة جودة الصور. القيم غياب ⇒ NULL (لا نخترع 0). القيد
    # chk_raster_quality_ratios يحرس 0..1 فيزيائيّاً؛ القائمة تُخزَّن jsonb.
    flags_json = json.dumps(index_quality_flags) if index_quality_flags is not None else None
    # v105 (v4-audit): أعمدة الجودة كانت تُنشأ في المخطّط لكن لا تُكتب أبداً ⇒ ترتيب
    # fetch_latest_asset حسب quality_score كان بلا أثر (كلّها NULL). نملؤها الآن من stats.
    mask_sources_json = json.dumps(cloud_mask_sources) if cloud_mask_sources is not None else None
    # FIX: asyncpg يطلب datetime.date لعمود DATE (تمرير نصّ ⇒ 'str' has no
    # attribute 'toordinal'). نحوّل النصّ ISO إلى date؛ القيم غير الصالحة → None.
    acq_date = acquisition_date
    if isinstance(acq_date, str):
        try:
            from datetime import date as _date

            acq_date = _date.fromisoformat(acq_date[:10]) if acq_date else None
        except ValueError:
            acq_date = None

    # v142/v145: idempotency على مستوى «المنتَج» لا مسار COG. ON CONFLICT على الفهرس
    # الفريد الجزئيّ (tenant/field/index/date/scene) — بلا cog_uri (v8-F6/v9-F8): مسار
    # COG عشوائيّ ({indicator}_{uuid}.tif) كان يُفلِت الفهرس فيُدرَج صفّ مكرّر لنفس المنتَج.
    # الآن cog_uri قيمة قابلة للتحديث (يشير الصفّ الوحيد إلى أحدث COG) لا جزء من الهويّة.
    sql = """
        INSERT INTO raster_assets (
            field_id, tenant_id, scene_id, acquisition_date, satellite,
            index_name, cloud_pct, srid, cog_uri, bands, nodata,
            footprint, provenance,
            valid_pixel_ratio, coverage_ratio, index_quality_flags,
            processing_job_id, quality_score, aoi_cloud_pct, cloud_mask_sources,
            geometry_revision, asset_status,
            product_identity_key, algorithm_version, qa_mask_version, field_geometry_hash
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9, $10::jsonb, $11,
            CASE WHEN $12::text IS NULL THEN NULL
                 ELSE ST_SetSRID(ST_GeomFromGeoJSON($12), 4326) END,
            $13::jsonb,
            $14, $15, COALESCE($16::jsonb, '[]'::jsonb),
            $17, $18, $19, COALESCE($20::jsonb, '[]'::jsonb),
            $21, $22,
            $23, $24, $25, $26
        )
        ON CONFLICT (product_identity_key)
        WHERE product_identity_key IS NOT NULL
        DO UPDATE SET
            cog_uri = EXCLUDED.cog_uri,
            cloud_pct = EXCLUDED.cloud_pct,
            bands = EXCLUDED.bands,
            provenance = EXCLUDED.provenance,
            valid_pixel_ratio = EXCLUDED.valid_pixel_ratio,
            coverage_ratio = EXCLUDED.coverage_ratio,
            index_quality_flags = EXCLUDED.index_quality_flags,
            processing_job_id = COALESCE(EXCLUDED.processing_job_id, raster_assets.processing_job_id),
            quality_score = EXCLUDED.quality_score,
            aoi_cloud_pct = EXCLUDED.aoi_cloud_pct,
            cloud_mask_sources = EXCLUDED.cloud_mask_sources,
            geometry_revision = COALESCE(EXCLUDED.geometry_revision, raster_assets.geometry_revision),
            asset_status = EXCLUDED.asset_status,
            algorithm_version = EXCLUDED.algorithm_version,
            qa_mask_version = EXCLUDED.qa_mask_version,
            field_geometry_hash = EXCLUDED.field_geometry_hash
    """
    try:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, false)",
            str(tenant_id) if tenant_id else "",
        )
        await conn.execute(
            sql,
            field_id,
            tenant_id,
            scene_id,
            acq_date,
            satellite,
            index_name,
            cloud_pct,
            srid,
            cog_uri,
            bands_json,
            nodata,
            footprint_geojson,
            provenance_json,
            valid_pixel_ratio,
            coverage_ratio,
            flags_json,
            processing_job_id,
            quality_score,
            aoi_cloud_pct,
            mask_sources_json,
            geometry_revision,
            asset_status,
            product_identity_key,
            algorithm_version,
            qa_mask_version,
            field_geometry_hash,
        )
        return True
    except Exception as e:  # noqa: BLE001 — صدق: لا نُفشل المعالجة لغياب القاعدة
        logger.warning("raster_assets insert skipped: %s", e)
        return False
    finally:
        await conn.close()


def _clamp_score_0_100(value) -> int | None:
    """يحوّل درجة جودة إلى int في [0,100] (قيد raster_registry/stac_item_registry).
    يقبل 0..1 (يضربها 100) أو 0..100 كما هي. None/غير رقميّ ⇒ None (لا اختراع)."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= v <= 1.0:
        v *= 100.0
    return max(0, min(100, int(round(v))))


async def insert_raster_registry_entry(
    *,
    tenant_id: str | None,
    field_id: str | None,
    scene_id: str | None,
    product_date: str | None,
    index_type: str,
    cog_url: str,
    cloud_pct: float | None,
    quality_score: int | None,
    resolution_m: float | None = 10.0,
    bbox: list | dict | None = None,
    bands: dict | list | None = None,
    metadata: dict | None = None,
) -> bool:
    """يجسر أصل راستر مُنتَج إلى كتالوج ``raster_registry`` (v114) — سدّ FINDING-008.

    raster_registry كان يكتبه فقط مسار REST يدويّ (/cog-registry)؛ الأنبوب لم يملأه ⇒
    كتالوج GIS فارغ. نكتب صفّاً مُقابِلاً عند كلّ أصل ناجح. best-effort (لا يُفشل المعالجة).
    RLS أصرم هنا (FORCE + WITH CHECK): نضبط app.current_tenant قبل الإدراج فيطابق tenant_id."""
    if not _valid_field_id_text(field_id) or not (tenant_id and _valid_uuid_text(tenant_id)):
        return False
    if not product_date or not cog_url:
        return False
    conn = await _connect()
    if conn is None:
        return False
    bbox_json = json.dumps(bbox) if bbox is not None else None
    bands_json = json.dumps(bands) if bands is not None else None
    meta_json = json.dumps(metadata or {})
    sql = """
        INSERT INTO raster_registry (
            tenant_id, field_id, scene_id, product_date, index_type, cog_url,
            cloud_pct, quality_score, resolution_m, bbox, bands, metadata
        ) VALUES (
            $1::uuid, $2, $3, $4::text::date, $5, $6,
            $7, $8, $9, $10::jsonb, COALESCE($11::jsonb, '{}'::jsonb), $12::jsonb
        )
        ON CONFLICT (tenant_id, field_id, product_date, index_type, cog_url)
        DO UPDATE SET
            scene_id = EXCLUDED.scene_id,
            cloud_pct = EXCLUDED.cloud_pct,
            quality_score = EXCLUDED.quality_score,
            resolution_m = EXCLUDED.resolution_m,
            bbox = EXCLUDED.bbox,
            bands = EXCLUDED.bands,
            metadata = raster_registry.metadata || EXCLUDED.metadata
    """
    try:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", str(tenant_id))
        await conn.execute(
            sql,
            str(tenant_id),
            field_id,
            scene_id,
            product_date[:10] if isinstance(product_date, str) else product_date,
            index_type,
            cog_url,
            cloud_pct,
            _clamp_score_0_100(quality_score),
            float(resolution_m) if resolution_m is not None else 10.0,
            bbox_json,
            bands_json,
            meta_json,
        )
        return True
    except Exception as e:  # noqa: BLE001 — الكتالوج best-effort لا يُفشل المعالجة
        logger.warning("raster_registry bridge skipped: %s", e)
        return False
    finally:
        await conn.close()


async def insert_stac_item(
    *,
    tenant_id: str | None,
    scene_id: str | None,
    collection: str,
    captured_at: str | None = None,
    bbox: list | dict | None = None,
    cloud_pct: float | None = None,
    quality_score: int | None = None,
    assets: dict | None = None,
    raw_item: dict | None = None,
) -> bool:
    """يستمرّ مشهد STAC مُختار في ``stac_item_registry`` (v114) — سدّ FINDING-009.

    الجدول كان بلا أيّ كاتب. نكتب المشهد عند اختياره في backfill. best-effort، RLS
    مضبوط بـapp.current_tenant قبل الإدراج."""
    if not (tenant_id and _valid_uuid_text(tenant_id)) or not scene_id:
        return False
    conn = await _connect()
    if conn is None:
        return False
    bbox_json = json.dumps(bbox) if bbox is not None else None
    assets_json = json.dumps(assets or {})
    raw_json = json.dumps(raw_item or {})
    sql = """
        INSERT INTO stac_item_registry (
            tenant_id, scene_id, collection, captured_at, bbox,
            cloud_pct, quality_score, assets, raw_item
        ) VALUES (
            $1::uuid, $2, $3, $4::text::timestamptz, $5::jsonb,
            $6, $7, COALESCE($8::jsonb, '{}'::jsonb), COALESCE($9::jsonb, '{}'::jsonb)
        )
        ON CONFLICT (tenant_id, scene_id)
        DO UPDATE SET
            collection = EXCLUDED.collection,
            captured_at = EXCLUDED.captured_at,
            bbox = EXCLUDED.bbox,
            cloud_pct = EXCLUDED.cloud_pct,
            quality_score = EXCLUDED.quality_score,
            assets = EXCLUDED.assets,
            raw_item = EXCLUDED.raw_item
    """
    try:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", str(tenant_id))
        await conn.execute(
            sql,
            str(tenant_id),
            scene_id,
            collection,
            captured_at,
            bbox_json,
            cloud_pct,
            _clamp_score_0_100(quality_score),
            assets_json,
            raw_json,
        )
        return True
    except Exception as e:  # noqa: BLE001 — الكتالوج best-effort
        logger.warning("stac_item_registry persist skipped: %s", e)
        return False
    finally:
        await conn.close()


async def insert_backfill_run(
    *,
    tenant_id: str | None,
    field_id: str | None,
    preset: str | None,
    from_date: str | None,
    to_date: str | None,
    months: int | None,
    indices: list | None,
    max_cloud_pct: float | None,
    geometry_revision: int | None = None,
    clip_polygon_geojson: dict | None = None,
    apply_cloud_mask: bool = True,
    limit_per_month: int = 2,
    source: str = "sentinel-2",
) -> int | None:
    """يُنشئ تشغيلة backfill (status='planned') ويُرجِع id — يمكّن الردّ الفوريّ بلا
    مسح STAC في مسار الطلب (v5-F1/F2). العامل يلتقطها لاحقاً. RLS: يضبط app.current_tenant."""
    if not _valid_field_id_text(field_id) or not (tenant_id and _valid_uuid_text(tenant_id)):
        return None
    conn = await _connect()
    if conn is None:
        return None
    sql = """
        INSERT INTO backfill_runs (
            tenant_id, field_id, preset, from_date, to_date, months, indices,
            max_cloud_pct, geometry_revision, clip_polygon_geojson, apply_cloud_mask,
            limit_per_month, source, status
        ) VALUES (
            $1::uuid, $2, $3, $4::text::date, $5::text::date, $6, COALESCE($7::jsonb, '[]'::jsonb),
            $8, $9, $10::jsonb, $11, $12, $13, 'planned'
        )
        RETURNING id
    """
    try:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", str(tenant_id))
        run_id = await conn.fetchval(
            sql,
            str(tenant_id),
            field_id,
            preset,
            from_date[:10] if isinstance(from_date, str) else from_date,
            to_date[:10] if isinstance(to_date, str) else to_date,
            months,
            json.dumps(indices or []),
            max_cloud_pct,
            geometry_revision,
            json.dumps(clip_polygon_geojson) if clip_polygon_geojson else None,
            apply_cloud_mask,
            int(limit_per_month),
            source,
        )
        return int(run_id) if run_id is not None else None
    except Exception as e:  # noqa: BLE001 — غياب الجدول لا يُفشل الطلب (يسقط للمسار المتزامن)
        logger.warning("backfill_runs insert skipped: %s", e)
        return None
    finally:
        await conn.close()


async def get_backfill_run_status(run_id: int, tenant_id: str | None = None) -> dict | None:
    """حالة تشغيلة backfill + عدّادات عناصرها المجمَّعة (v10-F10).

    يُرجِع status/عدّادات التشغيلة + تجميع فعليّ لـbackfill_run_items (persisted/failed/
    skipped/processing) كي لا تبقى الواجهة تعرض «نجاحاً» بلا رؤية للتقدّم الحقيقيّ.
    None إن غاب الصفّ/الجدول/القاعدة. مُصفّى بالمستأجِر (WHERE + app.current_tenant).
    """
    conn = await _connect()
    if conn is None:
        return None
    try:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, false)",
            str(tenant_id) if tenant_id else "",
        )
        run = await conn.fetchrow(
            """
            SELECT id, field_id, status, months_scanned, scenes_selected, jobs_scheduled,
                   items_persisted, items_failed, items_skipped, error,
                   created_at::text AS created_at, updated_at::text AS updated_at
            FROM backfill_runs
            WHERE id = $1 AND ($2::uuid IS NULL OR tenant_id = $2::uuid)
            """,
            int(run_id),
            str(tenant_id) if tenant_id else None,
        )
        if run is None:
            return None
        # تجميع حيّ لحالات العناصر (مصدر الحقيقة الفعليّ لا عدّادات التشغيلة وحدها).
        items = await conn.fetch(
            "SELECT status, count(*) AS n FROM backfill_run_items "
            "WHERE run_id = $1 GROUP BY status",
            int(run_id),
        )
        item_counts = {str(r["status"]): int(r["n"]) for r in items}
        out = dict(run)
        out["item_counts"] = item_counts
        return out
    except Exception as e:  # noqa: BLE001 — غياب الجدول لا يُفشل القراءة
        logger.warning("backfill_runs status fetch skipped (%s): %s", run_id, e)
        return None
    finally:
        await conn.close()


async def fetch_latest_asset(
    field_id: str,
    index_name: str,
    date: str | None = None,
    tenant_id: str | None = None,
) -> dict | None:
    """يقرأ أحدث COG مُخزَّن لحقل+مؤشّر من raster_assets (لإعادة ترطيب الذاكرة).

    هذا يسدّ ثغرة «persistence مكتوب لكن غير مقروء»: بعد إعادة تشغيل الخدمة أو
    على worker آخر، فهرس الطبقات في الذاكرة فارغ؛ نستعيد cog_uri + الحدود من
    القاعدة فيعمل عرض الشبكة/البلاطات على COG الموجود على القرص.

    يُرجِع dict {cog_url, index, acquisition_date, srid, bounds_4326} أو None.
    """
    conn = await _connect()
    if conn is None:
        return None
    sql = """
        SELECT cog_uri, acquisition_date::text AS acq, srid, cloud_pct,
               valid_pixel_ratio, coverage_ratio, index_quality_flags::text AS quality_flags,
               provenance #>> '{stats,confidence}' AS confidence,
               provenance #>> '{stats,quality}' AS quality,
               provenance #>> '{stats,cloud_mask_applied}' AS cloud_mask_applied,
               scene_id, geometry_revision, asset_status, processing_job_id,
               ST_XMin(env) AS minx, ST_YMin(env) AS miny,
               ST_XMax(env) AS maxx, ST_YMax(env) AS maxy
        FROM (
            SELECT cog_uri, acquisition_date, srid, cloud_pct,
                   valid_pixel_ratio, coverage_ratio, index_quality_flags,
                   provenance, scene_id, geometry_revision, asset_status, processing_job_id,
                   ST_Envelope(footprint) AS env
            FROM raster_assets
            WHERE field_id = $1 AND index_name = $2
              AND ($3::date IS NULL OR acquisition_date = $3::date)
              AND tenant_id = $4::uuid   -- فلتر مستأجِر صريح (دفاع عميق فوق RLS)؛ None ⇒ لا صفوف
              -- v9-F10/v11-F1: 'ready' حصراً — 'stale' (هندسة قديمة بعد تغيّر الحدود)
              -- لا يُقدَّم كصورة صالحة للخريطة. الاستعادة بإعادة معالجة تُنتج 'ready'.
              -- (يستفيد من idx_raster_assets_ready الجزئيّ WHERE asset_status='ready'.)
              AND asset_status = 'ready'
            -- أحدث تاريخ يفوز (دلالة latest)، ثمّ الأفضل جودةً (idx_raster_assets_quality_pick).
            ORDER BY acquisition_date DESC NULLS LAST,
                     quality_score DESC NULLS LAST,
                     cloud_pct ASC NULLS LAST,
                     created_at DESC
            LIMIT 1
        ) s
    """
    try:
        d = None if (date in (None, "", "latest")) else date
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, false)",
            str(tenant_id) if tenant_id else "",
        )
        row = await conn.fetchrow(
            sql, field_id, index_name, d, str(tenant_id) if tenant_id else None
        )
        if not row or not row["cog_uri"]:
            return None
        bounds = None
        if row["minx"] is not None:
            bounds = [row["minx"], row["miny"], row["maxx"], row["maxy"]]
        try:
            conf = float(row["confidence"]) if row["confidence"] is not None else None
        except (TypeError, ValueError):
            conf = None
        cloud_pct = float(row["cloud_pct"]) if row["cloud_pct"] is not None else None
        # v131 (v62.3-B): إشارات جودة الصور لمستهلكي المصب (v62.3-C).
        vpr = float(row["valid_pixel_ratio"]) if row["valid_pixel_ratio"] is not None else None
        cov = float(row["coverage_ratio"]) if row["coverage_ratio"] is not None else None
        flags = _parse_quality_flags(row["quality_flags"])
        return {
            "cog_url": row["cog_uri"],
            "index": index_name,
            "acquisition_date": row["acq"],
            "srid": row["srid"],
            "bounds_4326": bounds,
            "cloud_pct": cloud_pct,
            # cloud_cover نسبة [0..1] (cloud_pct/100) كي يستهلكها المصب مباشرةً.
            "cloud_cover": (cloud_pct / 100.0) if cloud_pct is not None else None,
            "valid_pixel_ratio": vpr,
            "coverage_ratio": cov,
            "index_quality_flags": flags,
            "confidence": conf,
            "quality": row["quality"],
            "cloud_mask_applied": str(row["cloud_mask_applied"]).lower() == "true"
            if row["cloud_mask_applied"] is not None
            else None,
            # v11-F4: نَسَب/هويّة الأصل — كي تحمل الطبقة المُعاد ترطيبها هذه الحقول
            # (field_id/geometry_revision/asset_status/scene_id/job) فيُميَّز ready/stale
            # ولا تعود شبكة بلا هويّة. field_id يُضيفه المُستدعي (معروف لديه).
            "scene_id": row["scene_id"],
            "geometry_revision": row["geometry_revision"],
            "asset_status": row["asset_status"],
            "processing_job_id": row["processing_job_id"],
        }
    except Exception as e:  # noqa: BLE001 — غياب القاعدة/الجدول لا يُفشل القراءة
        logger.warning("raster_assets fetch skipped: %s", e)
        return None
    finally:
        await conn.close()


async def list_asset_dates(
    field_id: str,
    index_name: str,
    tenant_id: str | None = None,
    limit: int = 800,
) -> list[str]:
    """List available acquisition dates for a field/index from raster_assets.

    Used by /v1/fields/{id}/timeseries when in-memory _field_layers is empty after
    restart. Returns ISO YYYY-MM-DD strings (ascending), tenant-filtered explicitly.

    السقف الافتراضيّ 800: سلسلة Sentinel-2 لسنتين ≈ 146 مروراً، ولـ3 سنوات ≈ 219،
    و5 سنوات ≈ 365 (قبل رفض الغيوم) — والحقل قد يحمل عدّة مؤشّرات. سقف 100 السابق كان
    يبتر أيّ backfill لسنتين+. والأهمّ: نأخذ الأحدث (DESC + LIMIT) لا الأقدم، لأنّ
    ASC+LIMIT كان يُبقي أقدم 100 تاريخ ويُسقط الأحدث — عكس المطلوب في شريط زمنيّ.
    نُرجِع النتيجة مفروزةً تصاعديّاً (يعتمد المُستدعي ترتيباً زمنيّاً).
    """
    conn = await _connect()
    if conn is None:
        return []
    # DESC + LIMIT ⇒ نحتفظ بأحدث `limit` تاريخاً؛ ثمّ نعكس للترتيب التصاعديّ.
    sql = """
        SELECT acq FROM (
            SELECT DISTINCT acquisition_date::text AS acq, acquisition_date AS ad
            FROM raster_assets
            WHERE field_id = $1 AND index_name = $2
              AND acquisition_date IS NOT NULL
              AND tenant_id = $3::uuid
              AND asset_status = 'ready'  -- v11-F1: الشريط الزمنيّ يعرض الجاهز فقط (لا stale)
            ORDER BY ad DESC
            LIMIT $4
        ) recent
        ORDER BY ad ASC
    """
    try:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, false)",
            str(tenant_id) if tenant_id else "",
        )
        rows = await conn.fetch(
            sql, field_id, index_name, str(tenant_id) if tenant_id else None, int(limit)
        )
        return [str(r["acq"])[:10] for r in rows if r["acq"]]
    except Exception as e:  # noqa: BLE001 — absence of DB/table should not break maps
        logger.warning("raster_assets date list skipped: %s", e)
        return []
    finally:
        await conn.close()


async def list_available_asset_dates(
    field_id: str,
    tenant_id: str | None = None,
    indices: list[str] | None = None,
    limit: int = 100,
) -> list[dict]:
    """List distinct persisted COG dates for a field, optionally restricted by indices.

    Returns rows with date, index_name, cloud_pct, scene_id and has_cog. This is
    deliberately tenant-filtered both by explicit WHERE and by app.current_tenant.
    """
    conn = await _connect()
    if conn is None:
        return []
    # الحدّ يُطبَّق على التواريخ المميَّزة (CTE) لا على صفوف (تاريخ×مؤشّر): مع N مؤشّرات
    # كان LIMIT على الصفوف يعيد ~limit/N تاريخاً فيبتر خطّ السنتين (v3-Finding-1).
    # ثمّ DISTINCT ON ينتقي صفّاً واحداً متماسكاً لكلّ (تاريخ، مؤشّر) بدل خلط
    # MIN(cloud_pct) مع MIN(scene_id) من صفَّين مختلفَين (v3-Finding-4): نفضّل صفّاً
    # يملك COG (has_cog محفوظ) ثمّ الأفضل جودةً — فيعود scene_id/cloud_pct/has_cog من نفس السطر.
    sql = """
        WITH recent_dates AS (
            SELECT DISTINCT acquisition_date
            FROM raster_assets
            WHERE field_id = $1
              AND tenant_id = $2::uuid
              AND acquisition_date IS NOT NULL
              AND asset_status = 'ready'  -- v11-F1: التواريخ المتاحة = الجاهزة فقط (لا stale)
              AND ($3::text[] IS NULL OR index_name = ANY($3::text[]))
            ORDER BY acquisition_date DESC
            LIMIT $4
        )
        SELECT DISTINCT ON (a.acquisition_date, a.index_name)
               a.acquisition_date::text AS date,
               a.index_name,
               a.cloud_pct,
               a.scene_id,
               -- وقت الالتقاط الحقيقيّ من كتالوج STAC (timestamptz) حين يتوفّر — لا نلفّق
               -- ساعة من DATE (acquisition_date تاريخ فقط بلا وقت). NULL ⇒ الواجهة تعرض
               -- التاريخ وحده بصدق (لا وقت مُختلَق).
               to_char(si.captured_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
                   AS acquisition_datetime,
               (a.cog_uri IS NOT NULL AND a.cog_uri <> '') AS has_cog
        FROM raster_assets a
        JOIN recent_dates rd ON rd.acquisition_date = a.acquisition_date
        LEFT JOIN stac_item_registry si
               ON si.tenant_id = a.tenant_id AND si.scene_id = a.scene_id
        WHERE a.field_id = $1
          AND a.tenant_id = $2::uuid
          AND a.asset_status = 'ready'  -- v11-F1: صفوف جاهزة فقط (لا stale/pending)
          AND ($3::text[] IS NULL OR a.index_name = ANY($3::text[]))
        ORDER BY a.acquisition_date DESC, a.index_name,
                 (a.cog_uri IS NOT NULL AND a.cog_uri <> '') DESC,
                 a.quality_score DESC NULLS LAST,
                 a.cloud_pct ASC NULLS LAST
    """
    try:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, false)",
            str(tenant_id) if tenant_id else "",
        )
        rows = await conn.fetch(
            sql,
            field_id,
            str(tenant_id) if tenant_id else None,
            list(indices) if indices else None,
            int(limit),
        )
        return [dict(r) for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("raster_assets available date list skipped: %s", e)
        return []
    finally:
        await conn.close()


class OwnerLookupUnavailable(Exception):
    """تعذّر إثبات ملكيّة الحقل رغم أنّ القاعدة **مُهيّأة** (DATABASE_URL مضبوط) —
    اتّصال/استعلام فاشل أو الدالّة غائبة. يُميَّز عن «وضع بلا قاعدة» (DATABASE_URL
    غير مضبوط) كي تستطيع المسارات المكشوفة fail-closed عند تعذّر الإثبات فقط، دون
    كسر التشغيل المقصود بلا قاعدة."""


async def field_owner_tenant(field_id: str) -> str | None:
    """مالك الحقل (tenant_id نصّاً) من المصدر الموثوق: جدول fields.

    تفويض ملكيّة الحقل: المسارات المكشوفة للمتصفّح تُنادى بالـfield_id فقط، ففحص
    الذاكرة (_field_layers) وحده يضعف بعد إعادة التشغيل/بلا طبقة مخبّأة. هنا نستعلم
    المالك الحقيقيّ عبر الدالّة SECURITY DEFINER `sahool_field_owner_tenant` (تتجاوز
    RLS/FORCE على fields فتقرأ المالك عبر المستأجرين، وتُعيد المعرّف فقط لا بيانات
    الحقل). field_id مفتاح أساسيّ ⇒ مالك واحد عالميّاً.

    تعاقُد الإرجاع:
    - نصّ المالك إن وُجد الحقل في fields.
    - None إن: (أ) DATABASE_URL غير مضبوط (وضع بلا قاعدة مقصود) أو (ب) الحقل غير
      موجود فعلاً (استعلام نجح بلا صفّ) — الحالتان لا تُوجبان الحجب.
    - يرفع OwnerLookupUnavailable إن كان DATABASE_URL **مضبوطاً** لكن تعذّر الاتّصال/
      الاستعلام/الدالّة غائبة ⇒ لا يمكن إثبات الملكيّة ⇒ يقرّر المنادي fail-closed."""
    if not DATABASE_URL:
        return None  # وضع بلا قاعدة مقصود — لا مصدر ملكيّة (يبقى فحص الذاكرة فقط)
    conn = await _connect()
    if conn is None:
        # DATABASE_URL مضبوط لكنّ الاتّصال فشل ⇒ الإثبات غير متاح (لا fail-safe صامت)
        raise OwnerLookupUnavailable(f"connect failed for field {field_id}")
    try:
        owner = await conn.fetchval("SELECT sahool_field_owner_tenant($1)", field_id)
        return str(owner) if owner else None  # مالك، أو None = غير موجود فعلاً
    except Exception as e:  # noqa: BLE001 — DB مُهيّأة لكن الاستعلام/الدالّة تعذّرا
        logger.warning("field_owner_tenant unavailable (%s): %s", field_id, type(e).__name__)
        raise OwnerLookupUnavailable(str(e)) from e
    finally:
        await conn.close()


async def layer_owner_tenant(layer_id: str) -> str | None:
    """مالك طبقة راستر persisted من raster_assets.

    fallback دفاعي لمسارات /tiles/{layer_id} بعد إعادة التشغيل عندما لا تكون
    _layers محمّلة في الذاكرة. لا يعيد بيانات الطبقة؛ فقط tenant_id.
    """
    if not DATABASE_URL:
        return None
    conn = await _connect()
    if conn is None:
        raise OwnerLookupUnavailable(f"connect failed for layer {layer_id}")
    sql = """
        SELECT tenant_id::text AS tenant_id
        FROM raster_assets
        WHERE processing_job_id = $1
           OR cog_uri ILIKE '%' || $1 || '%'
        ORDER BY created_at DESC
        LIMIT 1
    """
    try:
        owner = await conn.fetchval(sql, layer_id)
        return str(owner) if owner else None
    except Exception as e:  # noqa: BLE001
        logger.warning("layer_owner_tenant unavailable (%s): %s", layer_id, type(e).__name__)
        raise OwnerLookupUnavailable(str(e)) from e
    finally:
        await conn.close()


async def insert_field_geometry_version(
    *,
    field_id: str,
    tenant_id: str | None,
    geometry: dict,
    valid_from: str | None = None,
    reason: str | None = None,
) -> str | None:
    """Persist a versioned field geometry snapshot (best-effort).

    Historical imagery must be reproducible against the geometry that was valid at
    the time of analysis. This table is created by the enterprise imagery migration;
    absence of DB/table returns None instead of breaking raster flows.
    """
    conn = await _connect()
    if conn is None:
        return None
    geom_json = json.dumps(geometry)
    sql = """
        INSERT INTO field_geometry_versions (field_id, tenant_id, geometry, valid_from, reason)
        VALUES (
          $1, $2::uuid,
          ST_SetSRID(ST_GeomFromGeoJSON($3), 4326),
          COALESCE($4::timestamptz, now()),
          $5
        )
        RETURNING id::text
    """
    try:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, false)",
            str(tenant_id) if tenant_id else "",
        )
        return await conn.fetchval(
            sql, field_id, str(tenant_id) if tenant_id else None, geom_json, valid_from, reason
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("field_geometry_versions insert skipped: %s", e)
        return None
    finally:
        await conn.close()


async def fetch_field_analytics_for_export(
    *, tenant_id: str | None, field_ids: list[str] | None = None, limit: int = 10000
) -> list[dict]:
    """Fetch field/raster rows for GeoParquet export (best-effort)."""
    conn = await _connect()
    if conn is None:
        return []
    sql = """
        SELECT
          f.id::text AS field_id,
          f.tenant_id::text AS tenant_id,
          ST_AsGeoJSON(COALESCE(f.geom, f.geometry))::jsonb AS geometry,
          ra.index_name,
          ra.acquisition_date::text AS acquisition_date,
          ra.cloud_pct,
          ra.cog_uri
        FROM fields f
        LEFT JOIN raster_assets ra ON ra.field_id = f.id::text AND ra.tenant_id = f.tenant_id
        WHERE f.tenant_id = $1::uuid
          AND ($2::text[] IS NULL OR f.id::text = ANY($2::text[]))
        ORDER BY f.id::text, ra.acquisition_date DESC NULLS LAST
        LIMIT $3
    """
    try:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, false)",
            str(tenant_id) if tenant_id else "",
        )
        rows = await conn.fetch(sql, str(tenant_id) if tenant_id else None, field_ids, int(limit))
        return [dict(r) for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("field analytics export fetch skipped: %s", e)
        return []
    finally:
        await conn.close()


# ── إعادة دمج توحيد main↔cert: قراءة هندسة الحقل لقصّ CDSE poly ──
# (cert تفرّع قبل عمل CDSE في main؛ يحتاجها routers/cdse_tiles.py عبر _db.fetch_field_geometry)
async def fetch_field_geometry(field_id: str, tenant_id: str | None = None) -> dict | None:
    """يجلب geometry (JSONB) للحقل من جدول fields. يُرجع None إن تعذّر أو الحقل غير موجود.

    ⚠ **حرج (سبب جذريّ لفشل قصّ المضلّع):** جدول ``fields`` محميّ بـRLS/FORCE. بلا ضبط
    ``app.current_tenant`` لا يُرجِع الاستعلامُ أيَّ صفّ ⇒ ``geometry=None`` ⇒ تُمرَّر
    ``geometry=None`` إلى Sentinel Hub ⇒ بلاطات bbox مستطيلة بلا قصّ على المضلّع.
    لذا نحلّ المستأجِر المالك عبر الدالّة ``sahool_field_owner_tenant`` (SECURITY DEFINER —
    تتجاوز RLS) إن لم يُمرَّر ``tenant_id``، ثمّ نضبط السياق قبل القراءة (كبقيّة دوالّ هذا الملفّ).
    """
    conn = await _connect()
    if conn is None:
        return None
    try:
        if tenant_id is None:
            # المالك الموثوق دون كشف بيانات (يتجاوز RLS/FORCE على fields).
            tenant_id = await conn.fetchval("SELECT sahool_field_owner_tenant($1)", field_id)
        # is_local=false (جلسة) لا true (معاملة): asyncpg بلا معاملة صريحة = autocommit،
        # فـset_config(...,true) يضيع فور تنفيذه ⇒ يُفقَد سياق المستأجِر قبل fetchrow التالي
        # ⇒ RLS يعيد صفراً ⇒ geometry=None ⇒ بلاطة bbox بلا قصّ على المضلّع (العلّة الموصوفة
        # أعلاه). آمن: _connect() اتّصال جديد قصير العمر لكلّ عمليّة (لا pool، يُغلق في finally)
        # فلا تسرّب سياق. متّسق مع بقيّة دوالّ الملفّ (كلّها is_local=false).
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, false)",
            str(tenant_id) if tenant_id else "",
        )
        row = await conn.fetchrow("SELECT geometry FROM fields WHERE field_id = $1", field_id)
        if not row or row["geometry"] is None:
            return None
        geom = row["geometry"]
        if isinstance(geom, str):
            import json

            geom = json.loads(geom)
        return geom
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_field_geometry failed (%s): %s", field_id, e)
        return None
    finally:
        await conn.close()
