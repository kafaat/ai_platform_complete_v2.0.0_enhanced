"""عامل استهلاك طابور إبطال كاش الراستر (raster_cache_invalidations).

الفجوة (FINDING-005): الجدول ``raster_cache_invalidations`` (migrations/v96) طابورٌ
جاهز (status pending/processing/processed/failed + processed_at + فهرس جزئيّ) وله
مُنتِج (``mark_raster_cache_stale`` في المنصّة عند تغيّر هندسة الحقل) لكن **بلا أيّ
مستهلِك** — لا شيء يُبطِل بلاطات الكاش أو يعلّم الأصول البائتة.

هذا العامل يسدّ الفجوة على نمط Pattern A القانونيّ
(``services/sahool-platform/api/phase_runtime_workers.py``): poller مستقلّ يُطلَق
كخدمة compose، يطالب الصفوف بـ``FOR UPDATE SKIP LOCKED`` داخل معاملة، ثمّ لكلّ صفّ:
  (١) يحذف كامل بلاطات الحقل المُخبّأة على القرص (كلّ المؤشّرات/التواريخ)،
  (٢) يعلّم أصول الحقل الجاهزة ``asset_status='stale'`` (تبقى قابلة للخدمة حتّى
      إعادة المعالجة بالهندسة الجديدة — لا تُخفى، فقط تُوسَم للإبطال)،
  (٣) يضبط الصفّ ``processed``/``failed`` مع ``processed_at``.
ودوريّاً يُخلي كاش البلاطات المتجاوز (TTL/حصّة) عبر ``tile_cache_maint.prune_tile_cache`` —
سياسة احتفاظ لم تكن موجودة (FINDING-010).

صدق: لا يُعيد المعالجة (ذلك مسار refresh المعتاد الذي يحمل geometry_revision) — فقط
يُبطِل ويعلّم. غياب القاعدة/الجدول لا يُفشل الحلقة (يسجّل ويكمل)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import Any

import asyncpg
import tile_cache_maint  # وحدة خفيفة (بلا FastAPI): إبطال/إخلاء كاش البلاطات
from worker_heartbeat import HeartbeatState  # نبضة قدرة-واعية (V21 §2.2 / CT-06)

logger = logging.getLogger("raster-service.cache_invalidation_worker")

WORKER_POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "5"))
# دورة الإخلاء تُشغَّل كلّ N دورة استطلاع (تفادي مسح الشجرة كلّ ثانية).
PRUNE_EVERY_CYCLES = int(os.getenv("TILE_CACHE_PRUNE_EVERY_CYCLES", "60"))
# v11-F3/F5: قناة نشر إخلاء طبقات ذاكرة raster-service (نفس اسم القناة في main.py).
LAYER_EVICT_CHANNEL = os.getenv("RASTER_LAYER_EVICT_CHANNEL", "raster:layer_evict")

_redis_pub: Any = None


async def _publish_layer_evict(field_id: str) -> None:
    """ينشر ``field_id`` على قناة Redis كي تُخلي عمليّة raster-service طبقاته من الذاكرة.

    best-effort: عامل الإبطال يحذف بلاطات القرص ويعلّم DB stale، لكنّ ذاكرة الخدمة
    (عمليّة أخرى) تبقى تحمل الطبقة القديمة؛ هذا النشر يُخليها فوراً. غياب Redis/الحزمة
    أو فشل النشر لا يُفشل الإبطال (القرص+DB أُبطِلا فعلاً)."""
    global _redis_pub
    url = os.getenv("REDIS_URL")
    if not url or not field_id:
        return
    try:
        if _redis_pub is None:
            import redis.asyncio as _aioredis

            _redis_pub = _aioredis.from_url(url, encoding="utf-8", decode_responses=True)
        await _redis_pub.publish(LAYER_EVICT_CHANNEL, field_id)
    except Exception as e:  # noqa: BLE001 — النشر best-effort؛ القرص+DB أُبطِلا
        logger.warning("layer-evict publish skipped (field=%s): %s", field_id, e)


def _enabled() -> bool:
    """راية تفعيل: يُنشَر العامل كخدمة لكنّه خامل حتّى تأكيد التحقّق التكامليّ.
    يُقرأ في كلّ دورة (لا مرّة عند الإقلاع) كي يُفعَّل بلا إعادة نشر."""
    return str(os.getenv("RASTER_CACHE_INVALIDATION_ENABLED", "false")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


async def _connect() -> asyncpg.Pool:
    """تجمّع اتّصال عبر JOBS_DATABASE_URL (دور BYPASSRLS للعمّال) أو DATABASE_URL."""
    database_url = os.getenv("JOBS_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("JOBS_DATABASE_URL/DATABASE_URL مطلوب لعامل إبطال الكاش")
    return await asyncpg.create_pool(
        dsn=database_url, min_size=1, max_size=int(os.getenv("WORKER_DB_POOL_MAX", "4"))
    )


async def _set_tenant(conn: Any, tenant_id: Any) -> None:
    if tenant_id:
        await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant_id))


async def run_once(pool: asyncpg.Pool, *, batch_size: int = 50) -> int:
    """يعالج دفعة من الإبطالات المعلّقة. يُرجِع عدد الصفوف المُعالَجة."""
    async with pool.acquire() as conn:
        # المطالبة الذرّيّة: SELECT ... FOR UPDATE SKIP LOCKED ثمّ وسم processing داخل
        # معاملة واحدة — فلا يلتقط عاملان الصفّ نفسه (القفل يُحرَّر بعد الوسم).
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT id, tenant_id, field_id, reason
                FROM raster_cache_invalidations
                WHERE status = 'pending'
                ORDER BY created_at
                LIMIT $1
                FOR UPDATE SKIP LOCKED
                """,
                batch_size,
            )
            if rows:
                await conn.execute(
                    "UPDATE raster_cache_invalidations SET status='processing' "
                    "WHERE id = ANY($1::bigint[])",
                    [r["id"] for r in rows],
                )
        processed = 0
        for row in rows:
            rid = row["id"]
            tenant = str(row["tenant_id"]) if row["tenant_id"] else None
            field = row["field_id"]
            try:
                deleted = tile_cache_maint.invalidate_field_tile_cache(tenant, field)
                # v10-F6: set_config(...,true) عابرٌ للمعاملة — نُغلّف الضبط + التحديثات
                # المُعتمدة على المستأجِر في معاملة واحدة كي يبقى app.current_tenant سارياً
                # (يهمّ عند السقوط إلى DATABASE_URL بدور مقيّد بلا BYPASSRLS).
                async with conn.transaction():
                    await _set_tenant(conn, tenant)
                    staled = await conn.execute(
                        "UPDATE raster_assets SET asset_status='stale' "
                        "WHERE tenant_id = $1::uuid AND field_id = $2 AND asset_status = 'ready'",
                        tenant,
                        field,
                    )
                    await conn.execute(
                        "UPDATE raster_cache_invalidations "
                        "SET status='processed', processed_at=now() WHERE id=$1",
                        rid,
                    )
                # v11-F3/F5: أبلِغ عمليّة raster-service لتُخلي طبقات الحقل من الذاكرة
                # (بعد نجاح إبطال القرص+DB) — خارج المعاملة، best-effort.
                await _publish_layer_evict(field)
                processed += 1
                logger.info(
                    "invalidation processed id=%s field=%s tiles_deleted=%s assets=%s reason=%s",
                    rid,
                    field,
                    deleted,
                    staled,
                    row["reason"],
                )
            except Exception as e:  # noqa: BLE001 — صفّ واحد فاشل لا يُسقط الدفعة
                try:
                    await conn.execute(
                        "UPDATE raster_cache_invalidations "
                        "SET status='failed', processed_at=now() WHERE id=$1",
                        rid,
                    )
                except Exception:  # noqa: BLE001
                    pass
                logger.warning("invalidation failed id=%s field=%s: %s", rid, field, e)
        return processed


async def loop_worker() -> None:
    """حلقة الاستطلاع الدائمة: يعالج الإبطالات ثمّ ينام WORKER_POLL_SECONDS، ويُخلي
    كاش البلاطات المتجاوز دوريّاً. غياب القاعدة لا يُسقط الحلقة."""
    pool: asyncpg.Pool | None = None
    cycle = 0
    _logged_disabled = False
    # CT-06 (تدقيق الحاويات V21 §2.2): نبضة كلّ دورة تُثبِت أنّ حلقة الاستطلاع تتحرّك — يقرؤها
    # healthcheck الحاوية (حداثة + حالة) بدل مجرّد وجود متغيّر بيئة. خطأ المُشغّل يُسجَّل في
    # النبضة (state=failed) فيبقى الفحص أحمر ما دام العطل قائماً (تُعاد الحاوية بعد retries)،
    # ودورة ناجحة لاحقاً تُعيد الحالة إلى running — نُبقي تحمّل تأخّر الإقلاع (لا نُسقط الحلقة).
    hb = HeartbeatState(worker_name="raster-cache-invalidation")
    hb.write()
    while True:
        if not _enabled():
            if not _logged_disabled:
                logger.info(
                    "cache-invalidation worker خامل (RASTER_CACHE_INVALIDATION_ENABLED=false)"
                )
                _logged_disabled = True
            # النبضة تُكتَب حتّى في وضع الخمول: الحلقة حيّة (تستطلع الراية) فيبقى الفحص أخضر.
            hb.mark_poll(0)
            hb.write()
            await asyncio.sleep(WORKER_POLL_SECONDS)
            continue
        _logged_disabled = False
        try:
            if pool is None:
                pool = await _connect()
            processed = await run_once(pool)
            hb.mark_poll(processed)
            hb.write()
        except Exception as e:  # noqa: BLE001 — القاعدة قد تتأخّر عند الإقلاع؛ نُسجّل الفشل بالنبضة
            hb.mark_error(str(e))
            hb.write()
            logger.warning("cache-invalidation cycle skipped: %s", e)
            if pool is not None:
                try:
                    await pool.close()
                except Exception:  # noqa: BLE001
                    pass
            pool = None
        cycle += 1
        if PRUNE_EVERY_CYCLES > 0 and cycle % PRUNE_EVERY_CYCLES == 0:
            try:
                stats = tile_cache_maint.prune_tile_cache()
                if stats.get("deleted_ttl") or stats.get("deleted_quota"):
                    logger.info("tile cache pruned: %s", stats)
            except Exception as e:  # noqa: BLE001
                logger.warning("tile cache prune skipped: %s", e)
        await asyncio.sleep(WORKER_POLL_SECONDS)


def main_cli(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(description="raster cache-invalidation queue consumer")
    parser.add_argument("--once", action="store_true", help="عالِج دفعة واحدة ثمّ اخرج (للاختبار/CI)")
    args = parser.parse_args(argv)
    if args.once:

        async def _one() -> None:
            pool = await _connect()
            try:
                n = await run_once(pool)
                logger.info("processed %s invalidations", n)
            finally:
                await pool.close()

        asyncio.run(_one())
    else:
        asyncio.run(loop_worker())


if __name__ == "__main__":
    main_cli()
