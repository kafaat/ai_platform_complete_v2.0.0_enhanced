"""عامل فحص backfill الصور التاريخيّة (backfill_runs) — تدقيق الأقمار v5/v6.

الفجوة (v5-F1/F2 · v6-F1/F2/F4): نقطة ``/imagery/backfill`` كانت تمسح STAC شهريّاً
**داخل مسار الطلب** (حتّى 60 مكالمة لـ5 سنوات) فتتجاوز مهلة proxy المنصّة (60s)، وبلا
مفتاح idempotency تُكرّر المعالجة عند إعادة النقر.

هذا العامل (نمط Pattern A كعامل الإبطال) يستهلك ``backfill_runs``: يطالب تشغيلة
``planned`` (FOR UPDATE SKIP LOCKED بدور JOBS)، يمسح STAC شهريّاً **خارج مسار الطلب**،
ولكلّ (مشهد×مؤشّر):
  • preflight على ``raster_assets`` (تخطٍّ إن كان الأصل موجوداً — v6-F4)،
  • إدراج ``backfill_run_items`` بمفتاح idempotency فريد (ON CONFLICT DO NOTHING —
    إعادة النقر لا تُكرّر)،
  • معالجة COG عبر ``main._run_processing`` في threadpool (لا يحجب الحلقة).
ثمّ يُحدّث حالة التشغيلة (searching→queued→processing→completed/failed) وعدّاداتها.

يعيد استخدام دوالّ ``main`` (_stac_search/_rank_scenes/_month_windows/ProcessRequest/
_run_processing) — لا تكرار منطق. خامل حتّى ``RASTER_ASYNC_BACKFILL_ENABLED=true``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import asyncpg
import main  # يعيد استخدام مسح/ترتيب STAC ومعالجة COG (لا تكرار منطق)

logger = logging.getLogger("raster-service.backfill_scan_worker")

WORKER_POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "5"))


def _enabled() -> bool:
    return str(os.getenv("RASTER_ASYNC_BACKFILL_ENABLED", "false")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


async def _connect() -> asyncpg.Pool:
    database_url = os.getenv("JOBS_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("JOBS_DATABASE_URL/DATABASE_URL مطلوب لعامل فحص backfill")
    return await asyncpg.create_pool(
        dsn=database_url, min_size=1, max_size=int(os.getenv("WORKER_DB_POOL_MAX", "4"))
    )


async def _set_tenant(conn: Any, tenant_id: Any) -> None:
    if tenant_id:
        await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant_id))


def _idempotency_key(
    tenant: str, field: str, geom_rev, provider: str, scene: str, index: str
) -> str:
    return f"{tenant}:{field}:{geom_rev if geom_rev is not None else 0}:{provider}:{scene}:{index}"


async def run_once(pool: asyncpg.Pool) -> int:
    """يطالب تشغيلة planned واحدة ويعالجها. يُرجِع 1 إن عولجت تشغيلة، 0 إن لا شيء."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetch(
                """
                SELECT id, tenant_id, field_id, from_date, to_date, indices, max_cloud_pct,
                       geometry_revision, clip_polygon_geojson, apply_cloud_mask, limit_per_month
                FROM backfill_runs
                WHERE status = 'planned'
                ORDER BY created_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            )
            if not row:
                return 0
            run = dict(row[0])
            await conn.execute(
                "UPDATE backfill_runs SET status='searching', updated_at=now() WHERE id=$1",
                run["id"],
            )
    try:
        await _process_run(pool, run)
    except Exception as e:  # noqa: BLE001 — تشغيلة فاشلة لا تُسقط الحلقة
        logger.warning("backfill run %s failed: %s", run.get("id"), e)
        async with pool.acquire() as conn:
            try:
                await conn.execute(
                    "UPDATE backfill_runs SET status='failed', error=$2, updated_at=now() WHERE id=$1",
                    run["id"],
                    str(e)[:500],
                )
            except Exception:  # noqa: BLE001
                pass
    return 1


async def _process_run(pool: asyncpg.Pool, run: dict) -> None:
    run_id = run["id"]
    tenant = str(run["tenant_id"])
    field = run["field_id"]
    geom_rev = run["geometry_revision"]
    max_cloud = float(run["max_cloud_pct"]) if run["max_cloud_pct"] is not None else 30.0
    limit_per_month = int(run["limit_per_month"] or 2)
    indices = run["indices"] or []
    if isinstance(indices, str):
        indices = json.loads(indices)
    clip = run["clip_polygon_geojson"]
    if isinstance(clip, str):
        clip = json.loads(clip)
    bbox = main._bbox_from_geojson(clip) if clip else None
    if bbox is None:
        raise RuntimeError("clip_polygon_geojson مطلوب لاشتقاق bbox")

    start = _as_dt(run["from_date"])
    end = _as_dt(run["to_date"])
    windows = main._month_windows(start, end)

    # ١. مسح STAC شهريّاً خارج مسار الطلب (يستفيد من single-flight في العميل).
    selected: list[dict] = []
    months_scanned = 0
    for w_start, w_end in windows:
        search = await main._stac_search(
            bbox,
            w_start.strftime("%Y-%m-%dT00:00:00Z"),
            w_end.strftime("%Y-%m-%dT23:59:59Z"),
            max_cloud,
            limit=max(10, limit_per_month * 4),
        )
        items = main._rank_scenes(search.get("items", []), max_cloud_pct=max_cloud)[
            :limit_per_month
        ]
        selected.extend(items)
        months_scanned += 1

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE backfill_runs SET status='queued', months_scanned=$2, scenes_selected=$3, "
            "updated_at=now() WHERE id=$1",
            run_id,
            months_scanned,
            len(selected),
        )
        await conn.execute(
            "UPDATE backfill_runs SET status='processing', updated_at=now() WHERE id=$1", run_id
        )

    # ٢. لكلّ (مشهد×مؤشّر): idempotency + preflight + معالجة.
    jobs_scheduled = 0
    for scene in selected:
        scene_id = scene.get("item_id")
        acq = (scene.get("datetime") or "")[:10] or None
        if not scene_id:
            continue
        for index in indices:
            key = _idempotency_key(tenant, field, geom_rev, "element84", scene_id, index)
            async with pool.acquire() as conn:
                await _set_tenant(conn, tenant)
                # preflight: الأصل موجود بالفعل ⇒ تخطٍّ (لا إعادة معالجة). v6-F4.
                exists = await conn.fetchval(
                    "SELECT 1 FROM raster_assets WHERE tenant_id=$1::uuid AND field_id=$2 "
                    "AND index_name=$3 AND scene_id=$4 AND ($5::date IS NULL OR acquisition_date=$5::date) "
                    "AND asset_status <> 'failed' LIMIT 1",
                    tenant,
                    field,
                    index,
                    scene_id,
                    acq,
                )
                item_id = await conn.fetchval(
                    """
                    INSERT INTO backfill_run_items (
                        run_id, tenant_id, field_id, scene_id, index_name, acquisition_date,
                        provider, idempotency_key, status
                    ) VALUES ($1, $2::uuid, $3, $4, $5, $6::text::date, 'element84', $7, $8)
                    ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                    RETURNING id
                    """,
                    run_id,
                    tenant,
                    field,
                    scene_id,
                    index,
                    acq,
                    key,
                    "skipped" if exists else "queued",
                )
            if item_id is None:
                continue  # مفتاح مكرّر (نُقِر سابقاً) — idempotent، لا نُعيد
            if exists:
                continue  # الأصل موجود — سُجِّل skipped، لا معالجة
            ok = await asyncio.to_thread(
                _process_scene_index,
                scene,
                index,
                field,
                tenant,
                geom_rev,
                clip,
                run.get("apply_cloud_mask", True),
            )
            jobs_scheduled += 1
            async with pool.acquire() as conn:
                await _set_tenant(conn, tenant)
                await conn.execute(
                    "UPDATE backfill_run_items SET status=$2, processed_at=now() WHERE id=$1",
                    item_id,
                    "persisted" if ok else "failed",
                )

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE backfill_runs SET status='completed', jobs_scheduled=$2, updated_at=now() "
            "WHERE id=$1",
            run_id,
            jobs_scheduled,
        )
    logger.info(
        "backfill run %s completed field=%s months=%s scenes=%s jobs=%s",
        run_id,
        field,
        months_scanned,
        len(selected),
        jobs_scheduled,
    )


def _process_scene_index(
    scene: dict,
    index: str,
    field: str,
    tenant: str,
    geom_rev,
    clip: dict | None,
    apply_cloud_mask: bool,
) -> bool:
    """يبني VRT ويعالج مؤشّراً لمشهد (متزامن — يُستدعى عبر asyncio.to_thread). يُرجِع True عند النجاح."""
    import uuid as _uuid

    import stac_vrt

    jid = f"backfill_{_uuid.uuid4().hex[:12]}"
    try:
        safe_hrefs = {
            k: main._safe_raster_source(v) for k, v in (scene.get("bands_urls") or {}).items() if v
        }
        vrt_path, index_map = stac_vrt.build_band_vrt(safe_hrefs, out_dir=main.UPLOAD_DIR)
        preq = main.ProcessRequest(
            tenant_id=tenant,
            field_id=field,
            raster_url=vrt_path,
            indicator=main.IndicatorKind(index),
            source_format=main.SourceFormat.sentinel2_l2a,
            bands=main.BandMapping(
                **{k: v for k, v in index_map.items() if k in main.BandMapping.model_fields}
            ),
            clip_polygon_geojson=clip,
            apply_cloud_mask=bool(apply_cloud_mask),
            scene_id=scene.get("item_id"),
            capture_datetime=scene.get("datetime"),
            provider="element84",
            geometry_revision=geom_rev,
        )
        main._run_processing(jid, preq)
        job = main._jobs.get(jid) or {}
        return job.get("status") == main.JobStatus.completed
    except Exception as e:  # noqa: BLE001
        logger.warning("backfill scene %s/%s failed: %s", scene.get("item_id"), index, e)
        return False


def _as_dt(d) -> datetime:
    """يحوّل date/str إلى datetime بـUTC (لـ_month_windows)."""
    if isinstance(d, datetime):
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    if isinstance(d, str):
        d = datetime.fromisoformat(d[:10]).date()
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


async def loop_worker() -> None:
    pool: asyncpg.Pool | None = None
    logged_disabled = False
    while True:
        if not _enabled():
            if not logged_disabled:
                logger.info("backfill scan worker خامل (RASTER_ASYNC_BACKFILL_ENABLED=false)")
                logged_disabled = True
            await asyncio.sleep(WORKER_POLL_SECONDS)
            continue
        logged_disabled = False
        try:
            if pool is None:
                pool = await _connect()
            await run_once(pool)
        except Exception as e:  # noqa: BLE001 — القاعدة قد تتأخّر عند الإقلاع
            logger.warning("backfill scan cycle skipped: %s", e)
            if pool is not None:
                try:
                    await pool.close()
                except Exception:  # noqa: BLE001
                    pass
            pool = None
        await asyncio.sleep(WORKER_POLL_SECONDS)


def main_cli(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(description="raster backfill scan-run consumer")
    parser.add_argument("--once", action="store_true", help="عالِج تشغيلة واحدة ثمّ اخرج")
    args = parser.parse_args(argv)
    if args.once:

        async def _one() -> None:
            pool = await _connect()
            try:
                n = await run_once(pool)
                logger.info("processed %s backfill run(s)", n)
            finally:
                await pool.close()

        asyncio.run(_one())
    else:
        asyncio.run(loop_worker())


if __name__ == "__main__":
    main_cli()
