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

_pool = None


async def _get_pool():
    """ينشئ pool أسنكروني عند أوّل استخدام (إن توفّر DATABASE_URL + asyncpg)."""
    global _pool
    if _pool is not None:
        return _pool
    if not DATABASE_URL:
        return None
    try:
        import asyncpg
    except ImportError:
        return None
    try:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    except Exception as e:  # noqa: BLE001 — غياب القاعدة لا يُفشل المعالجة
        logger.warning("raster_assets pool unavailable: %s", e)
        return None
    return _pool


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
    pool = await _get_pool()
    if pool is None:
        return False

    footprint_geojson = json.dumps(footprint) if footprint else None
    bands_json = json.dumps(bands) if bands is not None else None
    provenance_json = json.dumps(provenance) if provenance else None

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
        async with pool.acquire() as conn:
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)",
                str(tenant_id) if tenant_id else "",
            )
            await conn.execute(
                sql,
                field_id,
                tenant_id,
                scene_id,
                acquisition_date,
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
