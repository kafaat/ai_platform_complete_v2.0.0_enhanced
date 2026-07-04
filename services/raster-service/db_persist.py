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
    # FIX: asyncpg يطلب datetime.date لعمود DATE (تمرير نصّ ⇒ 'str' has no
    # attribute 'toordinal'). نحوّل النصّ ISO إلى date؛ القيم غير الصالحة → None.
    acq_date = acquisition_date
    if isinstance(acq_date, str):
        try:
            from datetime import date as _date

            acq_date = _date.fromisoformat(acq_date[:10]) if acq_date else None
        except ValueError:
            acq_date = None

    sql = """
        INSERT INTO raster_assets (
            field_id, tenant_id, scene_id, acquisition_date, satellite,
            index_name, cloud_pct, srid, cog_uri, bands, nodata,
            footprint, provenance,
            valid_pixel_ratio, coverage_ratio, index_quality_flags
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9, $10::jsonb, $11,
            CASE WHEN $12::text IS NULL THEN NULL
                 ELSE ST_SetSRID(ST_GeomFromGeoJSON($12), 4326) END,
            $13::jsonb,
            $14, $15, COALESCE($16::jsonb, '[]'::jsonb)
        )
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
        )
        return True
    except Exception as e:  # noqa: BLE001 — صدق: لا نُفشل المعالجة لغياب القاعدة
        logger.warning("raster_assets insert skipped: %s", e)
        return False
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
               ST_XMin(env) AS minx, ST_YMin(env) AS miny,
               ST_XMax(env) AS maxx, ST_YMax(env) AS maxy
        FROM (
            SELECT cog_uri, acquisition_date, srid, cloud_pct,
                   valid_pixel_ratio, coverage_ratio, index_quality_flags,
                   provenance, ST_Envelope(footprint) AS env
            FROM raster_assets
            WHERE field_id = $1 AND index_name = $2
              AND ($3::date IS NULL OR acquisition_date = $3::date)
              AND tenant_id = $4::uuid   -- فلتر مستأجِر صريح (دفاع عميق فوق RLS)؛ None ⇒ لا صفوف
            ORDER BY acquisition_date DESC NULLS LAST, created_at DESC
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
    sql = """
        SELECT acquisition_date::text AS date, index_name,
               MIN(cloud_pct) AS cloud_pct,
               MIN(scene_id) AS scene_id,
               BOOL_OR(cog_uri IS NOT NULL AND cog_uri <> '') AS has_cog
        FROM raster_assets
        WHERE field_id = $1
          AND tenant_id = $2::uuid
          AND acquisition_date IS NOT NULL
          AND ($3::text[] IS NULL OR index_name = ANY($3::text[]))
        GROUP BY acquisition_date, index_name
        ORDER BY acquisition_date DESC
        LIMIT $4
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
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)",
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
