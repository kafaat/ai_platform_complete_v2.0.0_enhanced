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


# مهلة الإيجار (lease): تشغيلة عالقة في حالة غير نهائيّة أطول من هذا تُعتبر «عاملها مات»
# فتُستعاد (v9-F3). updated_at يُحدَّث عند كلّ انتقال، فهو نبض الحياة الفعليّ للتشغيلة.
_LEASE_TIMEOUT_SECONDS = int(os.getenv("BACKFILL_LEASE_TIMEOUT_SECONDS", "1800"))


async def run_once(pool: asyncpg.Pool) -> int:
    """يطالب تشغيلة planned (أو عالقة تجاوزت الإيجار) ويعالجها. يُرجِع 1 إن عولجت، 0 إن لا شيء."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # v9-F3: نلتقط planned، **أو** تشغيلة عالقة في حالة غير نهائيّة تجاوز
            # updated_at فيها مهلة الإيجار (عاملها مات بعد searching/queued/processing
            # فبقيت عالقة للأبد). FOR UPDATE SKIP LOCKED يمنع الالتقاط المزدوج.
            row = await conn.fetch(
                """
                SELECT id, tenant_id, field_id, from_date, to_date, indices, max_cloud_pct,
                       geometry_revision, clip_polygon_geojson, apply_cloud_mask, limit_per_month,
                       COALESCE(source, 'sentinel-2') AS source
                FROM backfill_runs
                WHERE status = 'planned'
                   OR (status IN ('searching', 'queued', 'processing')
                       AND updated_at < now() - make_interval(secs => $1))
                ORDER BY created_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
                _LEASE_TIMEOUT_SECONDS,
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
    # v147: مصدر التشغيلة (sentinel-2 افتراضاً · landsat-thermal للطبقة الحرارية الفريدة).
    # كان يُستعمَل أدناه بلا تعريف في رقعة Landsat ⇒ NameError على كلّ تشغيلة؛ نُعرّفه هنا.
    is_landsat_thermal = str(run.get("source") or "sentinel-2").strip().lower() == "landsat-thermal"
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
        if is_landsat_thermal:
            search = await main._stac_search_landsat_unique(
                bbox,
                w_start.strftime("%Y-%m-%dT00:00:00Z"),
                w_end.strftime("%Y-%m-%dT23:59:59Z"),
                max_cloud,
                limit=max(10, limit_per_month * 4),
            )
        else:
            try:
                search = await main._stac_search(
                    bbox,
                    w_start.strftime("%Y-%m-%dT00:00:00Z"),
                    w_end.strftime("%Y-%m-%dT23:59:59Z"),
                    max_cloud,
                    limit=max(10, limit_per_month * 4),
                    geometry=clip,  # CDSE catalog يستعمل intersects للقصّ الدقيق على الحقل
                )
            except TypeError as e:
                if "unexpected keyword argument 'geometry'" not in str(e):
                    raise
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
    # v9-F5: عدّادات نتائج دقيقة من الحفظ الفعليّ لا من عدد المحاولات (jobs_scheduled
    # يبقى للتوافق لكنّ صدق النجاح يقوم على items_persisted/failed/skipped).
    jobs_scheduled = 0
    items_persisted = 0
    items_failed = 0
    items_skipped = 0
    import uuid as _uuid

    for scene in selected:
        scene_id = scene.get("item_id")
        acq = (scene.get("datetime") or "")[:10] or None
        if not scene_id:
            continue
        for index in indices:
            provider_key = (
                "landsat-element84" if is_landsat_thermal else (scene.get("provider") or "cdse")
            )
            key = _idempotency_key(tenant, field, geom_rev, provider_key, scene_id, index)
            # v10-F6: set_config(...,true) عابرٌ للمعاملة؛ لذا نُغلّف الضبط + الاستعلامات
            # في معاملة واحدة كي يظلّ app.current_tenant سارياً (يهمّ حين يسقط العامل إلى
            # DATABASE_URL بدور مقيّد بلا BYPASSRLS — وإلّا رأت القراءات صفوفاً صفراً).
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await _set_tenant(conn, tenant)
                    # v10-F1: preflight يجب أن يطابق «أصلاً جاهزاً بنفس مراجعة الهندسة».
                    # 'stale' (هندسة قديمة بعد تغيّر الحدود) لا يُعدّ «موجوداً» وإلّا مُنِعت
                    # إعادة التوليد وبقيت الصورة مقصوصةً على حدود قديمة للأبد.
                    exists = await conn.fetchval(
                        "SELECT 1 FROM raster_assets WHERE tenant_id=$1::uuid AND field_id=$2 "
                        "AND index_name=$3 AND scene_id=$4 "
                        # acq نصّ (YYYY-MM-DD)؛ ``$5::date`` يجعل asyncpg يستنتج نوع date
                        # فيرفض الـstr («'str' has no attribute 'toordinal'»). ``$5::text::date``
                        # يُجبِر ربطاً نصّيّاً ثمّ يقصّه SQL — نفس نمط INSERT الآمن أدناه.
                        "AND ($5::text::date IS NULL OR acquisition_date=$5::text::date) "
                        "AND asset_status = 'ready' "
                        "AND ($6::int IS NULL OR geometry_revision = $6::int) LIMIT 1",
                        tenant,
                        field,
                        index,
                        scene_id,
                        acq,
                        geom_rev,
                    )
                    item_id = await conn.fetchval(
                        """
                        INSERT INTO backfill_run_items (
                            run_id, tenant_id, field_id, scene_id, index_name, acquisition_date,
                            provider, idempotency_key, status
                        ) VALUES ($1, $2::uuid, $3, $4, $5, $6::text::date, $9, $7, $8)
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
                        provider_key,
                    )
            if item_id is None:
                continue  # مفتاح مكرّر (نُقِر سابقاً) — idempotent، لا نُعيد
            if exists:
                items_skipped += 1
                continue  # الأصل موجود — سُجِّل skipped، لا معالجة
            # v9-F4: سجّل job_id ووسم processing **قبل** المعالجة كي يبقى الأثر
            # run_item → job → raster_asset واضحاً حتّى عند التعطّل أثناء المعالجة.
            jid = f"backfill_{_uuid.uuid4().hex[:12]}"
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await _set_tenant(conn, tenant)
                    await conn.execute(
                        "UPDATE backfill_run_items SET status='processing', job_id=$2 WHERE id=$1",
                        item_id,
                        jid,
                    )
            ok = await asyncio.to_thread(
                _process_scene_index,
                scene,
                index,
                field,
                tenant,
                geom_rev,
                clip,
                run.get("apply_cloud_mask", True),
                jid,
            )
            jobs_scheduled += 1
            if ok:
                items_persisted += 1
            else:
                items_failed += 1
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await _set_tenant(conn, tenant)
                    await conn.execute(
                        "UPDATE backfill_run_items SET status=$2, processed_at=now() WHERE id=$1",
                        item_id,
                        "persisted" if ok else "failed",
                    )

    # v8-F8/v9-F5: الحالة النهائيّة تعكس النتيجة الفعليّة لا مجرّد «انتهت الحلقة».
    final_status = "completed_with_errors" if items_failed > 0 else "completed"
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE backfill_runs SET status=$2, jobs_scheduled=$3, items_persisted=$4, "
            "items_failed=$5, items_skipped=$6, updated_at=now() WHERE id=$1",
            run_id,
            final_status,
            jobs_scheduled,
            items_persisted,
            items_failed,
            items_skipped,
        )
    logger.info(
        "backfill run %s %s field=%s months=%s scenes=%s persisted=%s failed=%s skipped=%s",
        run_id,
        final_status,
        field,
        months_scanned,
        len(selected),
        items_persisted,
        items_failed,
        items_skipped,
    )


def _process_scene_index(
    scene: dict,
    index: str,
    field: str,
    tenant: str,
    geom_rev,
    clip: dict | None,
    apply_cloud_mask: bool,
    jid: str,
) -> bool:
    """يبني VRT ويعالج مؤشّراً لمشهد (متزامن — يُستدعى عبر asyncio.to_thread). يُرجِع True عند النجاح.

    v9-F4: jid يُمرَّر من المُستدعي (لا يُولَّد داخليّاً) كي يُسجَّل على backfill_run_items
    قبل المعالجة — فيبقى أثر run_item → job → raster_asset حتّى عند التعطّل أثناء المعالجة.

    التحويل إلى CDSE: المشاهد المُكتشَفة من كتالوج CDSE تأتي بلا ``bands_urls`` (لا نطاقات
    COG) — تُعالَج عبر ``main._process_backfill_scene_cdse`` (Process API مثبَّت على تاريخ
    المشهد). المشاهد ذات ``bands_urls`` (ارتداد Element84) تبقى على مسار الـVRT."""
    import stac_vrt

    try:
        if (scene.get("provider") or "").startswith("landsat") or scene.get("thermal_urls"):
            if index != "lst":
                raise RuntimeError("landsat_derived_index_requires_lst_weather_ndvi")
            thermal_url = (scene.get("thermal_urls") or {}).get("lst")
            if not thermal_url:
                raise RuntimeError("landsat_lst_asset_missing")
            preq = main.ProcessRequest(
                tenant_id=tenant,
                field_id=field,
                raster_url=main._safe_raster_source(thermal_url),
                indicator=main.IndicatorKind.lst,
                source_format=main.SourceFormat.landsat8,
                bands=main.BandMapping(),
                precomputed_index=True,
                clip_polygon_geojson=clip,
                apply_cloud_mask=False,
                scene_id=scene.get("item_id"),
                capture_datetime=scene.get("datetime"),
                provider="landsat-element84",
                geometry_revision=geom_rev,
            )
            main._run_processing(jid, preq)
            job = main._jobs.get(jid) or {}
            result = job.get("result") or {}
            return bool(
                job.get("status") == main.JobStatus.completed and result.get("persisted") is True
            )

        if not (scene.get("bands_urls") or {}):
            # مشهد CDSE (كتالوج Copernicus): معالجة خادميّة عبر Process API.
            main._process_backfill_scene_cdse(scene, index, field, tenant, clip, geom_rev, jid)
            job = main._jobs.get(jid) or {}
            result = job.get("result") or {}
            return bool(
                job.get("status") == main.JobStatus.completed and result.get("persisted") is True
            )
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
        # v7-#2: «persisted» يجب أن يعني الحفظ في DB فعلاً، لا مجرّد اكتمال المعالجة.
        # _run_processing يضع result.persisted=False حين يفشل إدراج raster_assets (الصورة
        # في الذاكرة/القرص فقط). اعتماد status==completed وحده يمنح دليلاً كاذباً بالحفظ.
        result = job.get("result") or {}
        return bool(
            job.get("status") == main.JobStatus.completed and result.get("persisted") is True
        )
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
