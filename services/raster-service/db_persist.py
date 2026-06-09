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

logger = logging.getLogger("raster-service.db")

DATABASE_URL = os.getenv("DATABASE_URL", "")


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
) -> bool:
    """يُدرج صفّاً في raster_assets (best-effort). يُرجِع True عند النجاح.

    يضبط app.current_tenant عبر set_config قبل الإدراج (RLS). أيّ خطأ
    (لا قاعدة / لا جدول / لا شبكة) يُبتلع بصدق ويُرجِع False دون رمي.
    """
    conn = await _connect()
    if conn is None:
        return False

    footprint_geojson = json.dumps(footprint) if footprint else None
    bands_json = json.dumps(bands) if bands is not None else None
    provenance_json = json.dumps(provenance) if provenance else None
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
            footprint, provenance
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9, $10::jsonb, $11,
            CASE WHEN $12::text IS NULL THEN NULL
                 ELSE ST_SetSRID(ST_GeomFromGeoJSON($12), 4326) END,
            $13::jsonb
        )
    """
    try:
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)",
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
        SELECT cog_uri, acquisition_date::text AS acq, srid,
               ST_XMin(env) AS minx, ST_YMin(env) AS miny,
               ST_XMax(env) AS maxx, ST_YMax(env) AS maxy
        FROM (
            SELECT cog_uri, acquisition_date, srid, ST_Envelope(footprint) AS env
            FROM raster_assets
            WHERE field_id = $1 AND index_name = $2
              AND ($3::date IS NULL OR acquisition_date = $3::date)
            ORDER BY acquisition_date DESC NULLS LAST, created_at DESC
            LIMIT 1
        ) s
    """
    try:
        d = None if (date in (None, "", "latest")) else date
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)",
            str(tenant_id) if tenant_id else "",
        )
        row = await conn.fetchrow(sql, field_id, index_name, d)
        if not row or not row["cog_uri"]:
            return None
        bounds = None
        if row["minx"] is not None:
            bounds = [row["minx"], row["miny"], row["maxx"], row["maxy"]]
        return {
            "cog_url": row["cog_uri"],
            "index": index_name,
            "acquisition_date": row["acq"],
            "srid": row["srid"],
            "bounds_4326": bounds,
        }
    except Exception as e:  # noqa: BLE001 — غياب القاعدة/الجدول لا يُفشل القراءة
        logger.warning("raster_assets fetch skipped: %s", e)
        return None
    finally:
        await conn.close()
