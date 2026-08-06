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
  • معالجة COG عبر ``raster_processing_runtime`` في threadpool (لا يحجب الحلقة).
ثمّ يُحدّث حالة التشغيلة (searching→queued→processing→completed/failed) وعدّاداتها.

يعيد استخدام الوحدات المفككة مباشرةً بدلاً من استيراد ``main.py``؛ خامل حتّى
``RASTER_ASYNC_BACKFILL_ENABLED=true``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any, NamedTuple

import asyncpg
import raster_api_models as api_models
import raster_backfill_scene_processing
import raster_date_geo
import raster_processing_runtime
import raster_runtime_state
import raster_security_context
import raster_settings
import raster_stac_runtime
import scene_policy
import stac_search as stac_search_helpers
from worker_heartbeat import HeartbeatState  # نبضة قدرة-واعية (V21 §2.2 / CT-06)

logger = logging.getLogger("raster-service.backfill_scan_worker")

WORKER_POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "5"))


def _configure_stac_search() -> None:
    """Configure STAC helpers for the standalone worker without importing main.py."""
    raster_stac_runtime.configure_stac_search(logger=logger)


_configure_stac_search()


def _safe_raster_source(url: str | None) -> str:
    return raster_security_context.safe_raster_source(
        url, raster_settings.UPLOAD_DIR, raster_settings.SSRF_BLOCKED_HOSTS
    )


def _process_backfill_scene_cdse(
    scene: dict,
    index: str,
    field_id: str,
    tenant_id: str | None,
    clip: dict | None,
    geometry_revision,
    jid: str,
) -> None:
    ctx = raster_processing_runtime.make_processing_context()
    ctx._bbox_from_geojson = raster_date_geo.bbox_from_geojson
    ctx.IndicatorKind = api_models.IndicatorKind
    ctx.SourceFormat = api_models.SourceFormat
    ctx.BandMapping = api_models.BandMapping
    raster_backfill_scene_processing.process_backfill_scene_cdse(
        ctx, scene, index, field_id, tenant_id, clip, geometry_revision, jid
    )


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


def _identity(tenant, field, geom_rev, provider, scene, index, processing_version):
    """المسار الوحيد لبناء هويّة منتج الصور (V8-05 PR1-b) — مُشترَك بين الجماعيّ وsingle_scene."""
    from imagery_product_identity import ImageryProductIdentity

    return ImageryProductIdentity.create(
        tenant_id=tenant,
        field_id=field,
        geometry_revision=geom_rev,
        provider=provider,
        scene_id=scene,
        product=index,
        processing_version=processing_version,
    )


def _idempotency_key(
    tenant: str,
    field: str,
    geom_rev,
    provider: str,
    scene: str,
    index: str,
    processing_version: str,
) -> str:
    # v213/PR1-b: المفتاح القانونيّ v2 (يشمل processing_version) عبر كائن القيمة الوحيد.
    return _identity(
        tenant, field, geom_rev, provider, scene, index, processing_version
    ).to_canonical_key()


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
                       COALESCE(source, 'sentinel-2') AS source,
                       COALESCE(run_kind, 'backfill') AS run_kind
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
    bbox = raster_date_geo.bbox_from_geojson(clip) if clip else None
    if bbox is None:
        raise RuntimeError("clip_polygon_geojson مطلوب لاشتقاق bbox")

    # v213 (V8-05 PR1-a): تشغيلة «مشهد مفرد» تتفرّع هنا — لا اكتشاف شهريّ. العنصر الوحيد
    # مُنشأ مسبقاً (queued) من نقطة process-date؛ نحلّ المشهد المعروف لتاريخٍ واحد فقط ثمّ
    # نعالجه. يتفادى مسح STAC الطويل ويبقي مفتاح idempotency ونموذج الحالة كما هما.
    if str(run.get("run_kind") or "backfill") == "single_scene":
        await _process_single_scene_run(
            pool, run, bbox, clip, indices, is_landsat_thermal, max_cloud
        )
        return

    start = _as_dt(run["from_date"])
    end = _as_dt(run["to_date"])
    windows = raster_date_geo.month_windows(start, end)

    # ١. مسح STAC شهريّاً خارج مسار الطلب (يستفيد من single-flight في العميل).
    selected: list[dict] = []
    months_scanned = 0
    for w_start, w_end in windows:
        if is_landsat_thermal:
            search = await stac_search_helpers.stac_search_landsat_unique(
                bbox,
                w_start.strftime("%Y-%m-%dT00:00:00Z"),
                w_end.strftime("%Y-%m-%dT23:59:59Z"),
                max_cloud,
                limit=max(24, limit_per_month * 6),
            )
        else:
            try:
                search = await stac_search_helpers.stac_search(
                    bbox,
                    w_start.strftime("%Y-%m-%dT00:00:00Z"),
                    w_end.strftime("%Y-%m-%dT23:59:59Z"),
                    max_cloud,
                    limit=max(24, limit_per_month * 6),
                    geometry=clip,  # CDSE catalog يستعمل intersects للقصّ الدقيق على الحقل
                )
            except TypeError as e:
                if "unexpected keyword argument 'geometry'" not in str(e):
                    raise
                search = await stac_search_helpers.stac_search(
                    bbox,
                    w_start.strftime("%Y-%m-%dT00:00:00Z"),
                    w_end.strftime("%Y-%m-%dT23:59:59Z"),
                    max_cloud,
                    limit=max(24, limit_per_month * 6),
                )
        items = scene_policy.select_backfill_scenes_by_policy(
            search.get("items", []),
            indices=[str(i) for i in indices],
            max_cloud_pct=max_cloud,
            limit=limit_per_month,
        )
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

    from imagery_product_identity import canonical_processing_version

    proc_ver = canonical_processing_version()  # من مسار المعالجة القانونيّ لا من العميل

    for scene in selected:
        scene_id = scene.get("item_id")
        acq = (scene.get("datetime") or "")[:10] or None
        if not scene_id:
            continue
        for index in indices:
            provider_key = (
                "landsat-element84" if is_landsat_thermal else (scene.get("provider") or "cdse")
            )
            identity = _identity(tenant, field, geom_rev, provider_key, scene_id, index, proc_ver)
            key = identity.to_canonical_key()
            # v10-F6: set_config(...,true) عابرٌ للمعاملة؛ لذا نُغلّف الضبط + الاستعلامات
            # في معاملة واحدة كي يظلّ app.current_tenant سارياً (يهمّ حين يسقط العامل إلى
            # DATABASE_URL بدور مقيّد بلا BYPASSRLS — وإلّا رأت القراءات صفوفاً صفراً).
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await _set_tenant(conn, tenant)
                    # PR1-b dual-read: رحّل عنصراً قديماً (بلا processing_version) مطابقاً إلى
                    # المفتاح القانونيّ v2 مرّةً واحدةً (single-write) عند إمكان إثبات التطابق دون
                    # غموض (الإصدار الحاليّ = إصدار الأساس). لا إعادة كتابة جماعيّة.
                    if identity.legacy_matches_baseline():
                        await conn.execute(
                            "UPDATE backfill_run_items SET idempotency_key=$3 "
                            "WHERE tenant_id=$1::uuid AND idempotency_key=$2 "
                            "AND NOT EXISTS (SELECT 1 FROM backfill_run_items b2 "
                            "WHERE b2.tenant_id=$1::uuid AND b2.idempotency_key=$3)",
                            tenant,
                            identity.legacy_backfill_key(),
                            key,
                        )
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
                        # v12 incremental-backfill: المفتاح العالمي يمنع التكرار، لكن لا يجوز
                        # أن يمنع إعادة محاولة عنصر فشل سابقاً بسبب 429 أو تعطل مؤقت.
                        # القرار الصادق:
                        #   • إذا صار raster_asset جاهزاً فعلاً => skip.
                        #   • إذا لا يوجد أصل ready => أعد ربط العنصر الحالي بهذه التشغيلة
                        #     وأعده إلى queued ليُعاد السحب بدل أن يختفي بصمت.
                        if exists:
                            items_skipped += 1
                            continue
                        item_id = await conn.fetchval(
                            """
                            UPDATE backfill_run_items
                               SET run_id=$1, status='queued', job_id=NULL, error=NULL,
                                   processed_at=NULL
                             WHERE tenant_id=$2::uuid AND idempotency_key=$3
                             RETURNING id
                            """,
                            run_id,
                            tenant,
                            key,
                        )
            if item_id is None:
                # سباق نادر: عنصر تعذر إدراجه أو استعادته. لا نعلن نجاحاً ولا نرسل طلباً مكرراً.
                items_failed += 1
                continue
            if exists:
                items_skipped += 1
                continue  # الأصل موجود وجاهز — لا معالجة جديدة
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
            outcome = await asyncio.to_thread(
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
            if outcome.ok:
                items_persisted += 1
            else:
                items_failed += 1
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await _set_tenant(conn, tenant)
                    await conn.execute(
                        "UPDATE backfill_run_items SET status=$2, processed_at=now(), "
                        "error=$3 WHERE id=$1",
                        item_id,
                        "persisted" if outcome.ok else "failed",
                        outcome.reason,
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


async def _process_single_scene_run(
    pool: asyncpg.Pool,
    run: dict,
    bbox: list,
    clip: dict | None,
    indices: list,
    is_landsat_thermal: bool,
    max_cloud: float,
) -> None:
    """يعالج تشغيلة single_scene (v213): يحلّ مشهداً معروفاً لتاريخٍ واحد ويعالج عنصرها المُنشأ مسبقاً.

    بخلاف backfill لا اكتشاف شهريّ ولا اختيار سياسة: العنصر (queued) يحمل scene_id المستهدَف؛
    نمسح **نافذة يوم واحد** فقط لجلب روابط النطاقات ثمّ نطابق بالـitem_id ونعالج. الحدّ السحابيّ
    للحلّ مرفوع (المستخدم اختار المشهد صراحةً) — لا نستبعده بسحابة المشهد.
    """
    run_id = run["id"]
    tenant = str(run["tenant_id"])
    field = run["field_id"]
    geom_rev = run["geometry_revision"]
    apply_cloud_mask = run.get("apply_cloud_mask", True)
    day = _as_dt(run["from_date"])
    win_start = day.strftime("%Y-%m-%dT00:00:00Z")
    win_end = day.strftime("%Y-%m-%dT23:59:59Z")

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE backfill_runs SET status='processing', updated_at=now() WHERE id=$1", run_id
        )

    # مسح نافذة اليوم الواحد (حدّ سحابيّ مرفوع — المشهد مُختار صراحةً؛ الحلّ لا الاكتشاف).
    if is_landsat_thermal:
        search = await stac_search_helpers.stac_search_landsat_unique(
            bbox, win_start, win_end, 100, limit=24
        )
    else:
        try:
            search = await stac_search_helpers.stac_search(
                bbox, win_start, win_end, 100, limit=24, geometry=clip
            )
        except TypeError as e:
            if "unexpected keyword argument 'geometry'" not in str(e):
                raise
            search = await stac_search_helpers.stac_search(bbox, win_start, win_end, 100, limit=24)
    scenes_by_id = {s.get("item_id"): s for s in search.get("items", []) if s.get("item_id")}

    # العناصر المُنشأة مسبقاً لهذه التشغيلة (queued فقط — idempotency محفوظ في النقطة).
    async with pool.acquire() as conn:
        await _set_tenant(conn, tenant)
        items = await conn.fetch(
            "SELECT id, scene_id, index_name, acquisition_date::text AS acq "
            "FROM backfill_run_items WHERE run_id=$1 AND status='queued'",
            run_id,
        )

    items_persisted = 0
    items_failed = 0
    items_skipped = 0
    import uuid as _uuid

    for it in items:
        item_id = it["id"]
        scene_id = it["scene_id"]
        index = it["index_name"]
        acq = it["acq"]
        # preflight: أصبح الأصل جاهزاً بين الجدولة والالتقاط ⇒ تخطٍّ صادق (لا معالجة مكرّرة).
        async with pool.acquire() as conn:
            async with conn.transaction():
                await _set_tenant(conn, tenant)
                exists = await conn.fetchval(
                    "SELECT 1 FROM raster_assets WHERE tenant_id=$1::uuid AND field_id=$2 "
                    "AND index_name=$3 AND scene_id=$4 "
                    "AND ($5::text::date IS NULL OR acquisition_date=$5::text::date) "
                    "AND asset_status='ready' "
                    "AND ($6::int IS NULL OR geometry_revision=$6::int) LIMIT 1",
                    tenant,
                    field,
                    index,
                    scene_id,
                    acq,
                    geom_rev,
                )
        if exists:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await _set_tenant(conn, tenant)
                    await conn.execute(
                        "UPDATE backfill_run_items SET status='skipped', processed_at=now() "
                        "WHERE id=$1",
                        item_id,
                    )
            items_skipped += 1
            continue
        scene = scenes_by_id.get(scene_id)
        if scene is None:
            # المشهد المستهدَف غير موجود في كتالوج اليوم (سُحب/تغيّر) ⇒ فشل صادق لا اختلاق.
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await _set_tenant(conn, tenant)
                    await conn.execute(
                        "UPDATE backfill_run_items SET status='failed', processed_at=now(), "
                        "error=$2 WHERE id=$1",
                        item_id,
                        "scene_not_found_in_catalog_for_date",
                    )
            items_failed += 1
            continue
        jid = f"single_{_uuid.uuid4().hex[:12]}"
        async with pool.acquire() as conn:
            async with conn.transaction():
                await _set_tenant(conn, tenant)
                await conn.execute(
                    "UPDATE backfill_run_items SET status='processing', job_id=$2 WHERE id=$1",
                    item_id,
                    jid,
                )
        outcome = await asyncio.to_thread(
            _process_scene_index, scene, index, field, tenant, geom_rev, clip, apply_cloud_mask, jid
        )
        if outcome.ok:
            items_persisted += 1
        else:
            items_failed += 1
        async with pool.acquire() as conn:
            async with conn.transaction():
                await _set_tenant(conn, tenant)
                await conn.execute(
                    "UPDATE backfill_run_items SET status=$2, processed_at=now(), "
                    "error=$3 WHERE id=$1",
                    item_id,
                    "persisted" if outcome.ok else "failed",
                    outcome.reason,
                )

    final_status = "completed_with_errors" if items_failed > 0 else "completed"
    # مراجعة P2-1: jobs_scheduled يعدّ العناصر التي **جُدولت لها وظيفة فعلاً** (انتقلت إلى
    # processing بمعرّف job) = المُثبَّتة + الفاشلة؛ المتخطّاة (أصبحت جاهزة قبل الالتقاط) لم
    # تُجدوَل وظيفة. مساواته بـitems_persisted وحدها كانت تُخفي الوظائف التي شُغّلت وفشلت.
    jobs_scheduled = items_persisted + items_failed
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE backfill_runs SET status=$2, jobs_scheduled=$3, items_persisted=$4, "
            "items_failed=$5, items_skipped=$6, scenes_selected=$7, months_scanned=1, "
            "updated_at=now() WHERE id=$1",
            run_id,
            final_status,
            jobs_scheduled,
            items_persisted,
            items_failed,
            items_skipped,
            len(items),
        )
    logger.info(
        "single_scene run %s %s field=%s persisted=%s failed=%s skipped=%s",
        run_id,
        final_status,
        field,
        items_persisted,
        items_failed,
        items_skipped,
    )


class SceneOutcome(NamedTuple):
    """نتيجة معالجة مشهد: النجاح **وسببُ الفشل** — لا bool يُسقِط السبب.

    ``BACKFILL-FAILURE-REASON-DISCARDED-01``. كان المُرجَع ``bool``، فتنهار ثلاث حالات
    فشل متمايزة إلى ``False`` واحد: استثناء · وظيفة لم تكتمل · **عولجت ولم تُحفَظ**.
    والسبب يُسجَّل في سجلّ العامل ثمّ يُرمى، بينما ``backfill_run_items.error`` عمودٌ
    قائم يبقى ``NULL`` — و``db_persist.get_backfill_run_status`` يقرأ ``error`` ويعرضه،
    فالواجهة مبنيّة لعرض سببٍ لا يصل. المُشغِّل يرى «٣ فاشلة» بلا سبب واحد.
    """

    ok: bool
    reason: str | None = None


def _outcome_from_job(jid: str) -> SceneOutcome:
    """يقرأ حالة الوظيفة ويُترجمها إلى نتيجة **بسببها** — نقطةٌ واحدة للمسارات الثلاثة.

    لِـ``_process_scene_index`` ثلاثة مسارات معالجة (Landsat · CDSE · VRT)، وكلّها كانت
    تنتهي بالتعبير ``bool(status == completed and persisted is True)`` **مكرّراً حرفيّاً**.
    تحويلُ واحدٍ منها وحده تركَ الآخرَين يُرجِعان ``bool`` بينما يقرأ المُستدعي
    ``outcome.ok`` ⇒ ``AttributeError`` على المسار الأشيع (CDSE). **التكرار هو ما جعل
    الإصلاح الجزئيّ ممكناً**، ولم يكشفه إلّا تكذيبُ حارس «الحقيقة التشغيليّة»؛ فصار
    المنطق في موضع واحد لا ثلاثة.

    و«persisted» يعني الحفظ في DB فعلاً لا اكتمال المعالجة: ``run_processing`` يضع
    ``result.persisted=False`` حين يفشل إدراج ``raster_assets`` (الصورة في الذاكرة/القرص
    فقط)، فاعتماد ``status==completed`` وحده يمنح دليلاً كاذباً بالحفظ.
    """
    job = raster_runtime_state.JOBS.get(jid) or {}
    result = job.get("result") or {}
    if job.get("status") != api_models.JobStatus.completed:
        return SceneOutcome(False, f"job_not_completed:{job.get('status')}")
    if result.get("persisted") is not True:
        # أخطر الحالات: العمل تمّ والأثر ضاع، وكانت تُقرأ «فشلاً» لا يُميَّز عن انقطاع شبكة.
        return SceneOutcome(False, "processed_not_persisted")
    return SceneOutcome(True)


def _process_scene_index(
    scene: dict,
    index: str,
    field: str,
    tenant: str,
    geom_rev,
    clip: dict | None,
    apply_cloud_mask: bool,
    jid: str,
) -> SceneOutcome:
    """يبني VRT ويعالج مؤشّراً لمشهد (متزامن — يُستدعى عبر asyncio.to_thread).

    يُرجِع ``SceneOutcome(ok, reason)``؛ و``reason`` **رمزٌ ثابت + نوع الاستثناء +
    مُعرّف ربط**، لا نصّ الاستثناء: العمود يُقرأ عبر ``get_backfill_run_status`` ضمن
    مستأجِر، ونصّ استثناء قد يحمل سلسلة اتّصال. التفاصيل الكاملة في السجلّ بالمُعرّف نفسه.

    v9-F4: jid يُمرَّر من المُستدعي (لا يُولَّد داخليّاً) كي يُسجَّل على backfill_run_items
    قبل المعالجة — فيبقى أثر run_item → job → raster_asset حتّى عند التعطّل أثناء المعالجة.

    التحويل إلى CDSE: مشاهد truecolor دائماً عبر CDSE (Fix 2: تجنّب قراءة النطاق الكامل OOM).
    المشاهد بلا ``bands_urls`` (كتالوج Copernicus) عبر Process API مثبَّت على تاريخ المشهد.
    المشاهد ذات ``bands_urls`` (ارتداد Element84) تبقى على مسار الـVRT."""
    import stac_vrt

    try:
        if (scene.get("provider") or "").startswith("landsat") or scene.get("thermal_urls"):
            if index != "lst":
                raise RuntimeError("landsat_derived_index_requires_lst_weather_ndvi")
            thermal_url = (scene.get("thermal_urls") or {}).get("lst")
            if not thermal_url:
                raise RuntimeError("landsat_lst_asset_missing")
            preq = api_models.ProcessRequest(
                tenant_id=tenant,
                field_id=field,
                raster_url=_safe_raster_source(thermal_url),
                indicator=api_models.IndicatorKind.lst,
                source_format=api_models.SourceFormat.landsat8,
                bands=api_models.BandMapping(),
                precomputed_index=True,
                clip_polygon_geojson=clip,
                apply_cloud_mask=False,
                scene_id=scene.get("item_id"),
                capture_datetime=scene.get("datetime"),
                provider="landsat-element84",
                geometry_revision=geom_rev,
            )
            raster_processing_runtime.run_processing(jid, preq)
            return _outcome_from_job(jid)

        # Fix 2: truecolor عبر CDSE دائماً — مسار Element84/VRT يقرأ النطاق كاملاً
        # (10980×10980 px ≈ 1.4 GB) ويُعطَل بـOOM. CDSE يقصّ خادميّاً قبل الإرسال.
        if index == "truecolor" or not (scene.get("bands_urls") or {}):
            # مشهد CDSE أو truecolor: معالجة خادميّة عبر Process API.
            _process_backfill_scene_cdse(scene, index, field, tenant, clip, geom_rev, jid)
            return _outcome_from_job(jid)
        safe_hrefs = {
            k: _safe_raster_source(v) for k, v in (scene.get("bands_urls") or {}).items() if v
        }
        vrt_path, index_map = stac_vrt.build_band_vrt(
            safe_hrefs, out_dir=raster_settings.UPLOAD_DIR
        )
        preq = api_models.ProcessRequest(
            tenant_id=tenant,
            field_id=field,
            raster_url=vrt_path,
            indicator=api_models.IndicatorKind(index),
            source_format=api_models.SourceFormat.sentinel2_l2a,
            bands=api_models.BandMapping(
                **{k: v for k, v in index_map.items() if k in api_models.BandMapping.model_fields}
            ),
            clip_polygon_geojson=clip,
            apply_cloud_mask=bool(apply_cloud_mask),
            scene_id=scene.get("item_id"),
            capture_datetime=scene.get("datetime"),
            provider="element84",
            geometry_revision=geom_rev,
        )
        raster_processing_runtime.run_processing(jid, preq)
        return _outcome_from_job(jid)
    except Exception as e:  # noqa: BLE001
        import uuid as _uuid_local

        correlation_id = _uuid_local.uuid4().hex[:12]
        logger.warning(
            "backfill scene %s/%s failed [%s]: %s",
            scene.get("item_id"),
            index,
            correlation_id,
            e,
        )
        return SceneOutcome(False, f"exception:{type(e).__name__}:{correlation_id}")


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
    # CT-06 (تدقيق الحاويات V21 §2.2): نبضة كلّ دورة تُثبِت أنّ حلقة الاستطلاع تتحرّك — يقرؤها
    # healthcheck الحاوية (حداثة + حالة) بدل مجرّد وجود متغيّر بيئة. خطأ المُشغّل يُسجَّل في
    # النبضة (state=failed) فيبقى الفحص أحمر ما دام العطل قائماً (تُعاد الحاوية بعد retries)،
    # ودورة ناجحة لاحقاً تُعيد الحالة إلى running — نُبقي رؤية انحراف المخطّط + تحمّل العابر.
    hb = HeartbeatState(worker_name="raster-backfill-scan")
    hb.write()
    while True:
        if not _enabled():
            if not logged_disabled:
                logger.info("backfill scan worker خامل (RASTER_ASYNC_BACKFILL_ENABLED=false)")
                logged_disabled = True
            # النبضة تُكتَب حتّى في وضع الخمول: الحلقة حيّة (تستطلع الراية) فيبقى الفحص أخضر.
            hb.mark_poll(0)
            hb.write()
            await asyncio.sleep(WORKER_POLL_SECONDS)
            continue
        logged_disabled = False
        try:
            if pool is None:
                pool = await _connect()
            processed = await run_once(pool)
            hb.mark_poll(processed)
            hb.write()
        except (asyncpg.UndefinedColumnError, asyncpg.UndefinedTableError) as e:
            # خطأ مخطّط دائم (عمود/جدول مفقود بعد ترحيل ناقص) — ليس عابراً كتأخّر الإقلاع.
            # لو بقي عند warning لظلّ العلوق صامتاً: استعلام المطالبة يفشل كلّ دورة فتتراكم
            # التشغيلات في 'planned' بلا إشارة. نرفعه إلى ERROR بتلميح صريح للترحيل ونُسجّله
            # في النبضة (state=failed) كي يفشل الفحص الصحّيّ ما دام الانحراف قائماً.
            hb.mark_error(str(e))
            hb.write()
            logger.error(
                "backfill scan BLOCKED by schema drift (runs will stay 'planned' forever): %s — "
                "apply pending migrations (v144–v147: backfill_runs + source column, "
                "scripts_v9/run_migrations.sql steps 150–153)",
                e,
            )
            if pool is not None:
                try:
                    await pool.close()
                except Exception:  # noqa: BLE001
                    pass
            pool = None
        except Exception as e:  # noqa: BLE001 — القاعدة قد تتأخّر عند الإقلاع (عابر)؛ نُسجّله بالنبضة
            hb.mark_error(str(e))
            hb.write()
            logger.warning("backfill scan cycle skipped (transient, e.g. DB warming up): %s", e)
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
