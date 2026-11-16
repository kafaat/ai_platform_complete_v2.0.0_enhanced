"""عامل استهلاك طابور إبطال كاش الراستر (raster_cache_invalidations).

الفجوة (FINDING-005): الجدول ``raster_cache_invalidations`` (migrations/v96) طابورٌ
جاهز (status pending/processing/processed/failed + processed_at + فهرس جزئيّ) وله
مُنتِج (``mark_raster_cache_stale`` في المنصّة عند تغيّر هندسة الحقل) لكن **بلا أيّ
مستهلِك** — لا شيء يُبطِل بلاطات الكاش أو يعلّم الأصول البائتة.

هذا العامل يسدّ الفجوة على نمط Pattern A القانونيّ
(``services/sahool-platform/api/phase_runtime_workers.py``): poller مستقلّ يُطلَق
كخدمة compose، يطالب الصفوف بـ``FOR UPDATE SKIP LOCKED`` داخل معاملة، ثمّ لكلّ صفّ:
  (١) يحذف كامل بلاطات الحقل المُخبّأة على القرص (كلّ المؤشّرات/التواريخ)،
  (٢) يعلّم أصول الحقل الجاهزة **السابقة للتغيير الذي يُسمّيه الإبطال** ``asset_status='stale'``
      (``invalidation_scope``) — لا كلَّ أصلٍ جاهز. قرّاءُ العرض يقرؤون ``ready`` حصراً، فوسمُ
      أصلٍ مبنيٍّ على الهندسة الجديدة يُخفيه (مصغّرةٌ 404)،
  (٣) يضبط الصفّ ``processed``/``failed`` مع ``processed_at``.
المطالبةُ **إجارةٌ تنقضي** (C1): ``metadata.lease_until`` + ``claim_attempts``، والصفُّ
``processing`` المنقضيةُ إجارتُه يُستعاد (عاملٌ مات بعد التزام المطالبة لا يُعلِّقه إلى الأبد)،
ومستنفِدُ المحاولات يُنهى ``failed`` لا يُعاد بلا حدّ. وإخلاءُ ذاكرة الخدمة عبر Redis جزءٌ من
الإنجاز (P3-INV): نشرٌ فاشل يُحرِّر الصفَّ ``pending`` بمهلة ``retry_after`` ويُسجِّل
``layer_evict='not_delivered'`` — لا يُعَدّ نجاحاً.
ودوريّاً يُخلي كاش البلاطات المتجاوز (TTL/حصّة) عبر ``tile_cache_maint.prune_tile_cache`` —
سياسة احتفاظ لم تكن موجودة (FINDING-010).

صدق: لا يُعيد المعالجة (ذلك مسار refresh المعتاد الذي يحمل geometry_revision) — فقط
يُبطِل ويعلّم. غياب القاعدة/الجدول لا يُفشل الحلقة (يسجّل ويكمل)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime
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
# C1: مهلةُ إجارة المطالبة — صفٌّ ``processing`` تجاوزها يُعتبَر «عاملُه مات» فيُستعاد.
# تغطّي دفعةً كاملة (حذفُ دليل بلاطات + عبارتان لكلّ صفّ)؛ الاستعادةُ المبكّرة آمنة لأنّ
# العمل idempotent (الحذفُ والوسمُ المقيّدُ بالتغيير المُسمّى يُعادان بلا أثرٍ إضافيّ).
CLAIM_LEASE_SECONDS = float(os.getenv("CACHE_INVALIDATION_LEASE_SECONDS", "300"))
# حدُّ المطالبات لصفٍّ واحد: صفٌّ يُميت العاملَ أو لا يُسلَّم إخلاؤه في كلّ مرّة يُنهى
# ``failed`` بعد هذا العدد بدل حلقةٍ بلا نهاية.
MAX_CLAIM_ATTEMPTS = int(os.getenv("CACHE_INVALIDATION_MAX_ATTEMPTS", "5"))
# P3-INV: مهلةُ إعادة المحاولة بعد نشر إخلاءٍ فاشل (× رقم المحاولة — تراجعٌ خطّيّ).
RETRY_BACKOFF_SECONDS = float(os.getenv("CACHE_INVALIDATION_RETRY_BACKOFF_SECONDS", "30"))

# مفاتيحُ حالة العامل في ``metadata`` — يكتبها العامل وحده. ``metadata`` نفسُه يملؤه المُستدعي
# (``CacheInvalidationCommand.metadata``)، فيُسقطها الإدراجُ من مُدخَله
# (``db_persist.CACHE_INVALIDATION_WORKER_KEYS`` — نسخةٌ يقارنها اختبار)، والعاملُ يقرؤها
# بصبٍّ محروسٍ بالنوع: قيمةٌ غيرُ صالحة تُقرأ غائبةً لا تُسقط مطالبةَ الدفعة لكلّ المستأجِرين.
# ``lease_until``/``retry_after`` عددُ ثوانٍ منذ الحقبة (لا نصُّ لحظة): صبُّ عددِ JSON إلى
# ``numeric`` لا يفشل، وصبُّ نصٍّ إلى ``timestamptz`` يفشل على 'x' (و``pg_input_is_valid``
# من PG16 والمكدّس يحمل PG15 أيضاً).
WORKER_METADATA_KEYS = frozenset(
    {"claim_attempts", "lease_until", "retry_after", "layer_evict", "last_error"}
)

# نتيجةُ نشر الإخلاء كما تُسجَّل على الصفّ (``metadata.layer_evict``).
LAYER_EVICT_DELIVERED = "delivered"
LAYER_EVICT_NOT_CONFIGURED = "not_configured"
LAYER_EVICT_NOT_DELIVERED = "not_delivered"

_redis_pub: Any = None


async def _publish_layer_evict(field_id: str) -> str:
    """ينشر ``field_id`` على قناة Redis كي تُخلي عمليّة raster-service طبقاته من الذاكرة.

    عامل الإبطال يحذف بلاطات القرص ويعلّم DB stale، لكنّ ذاكرة الخدمة (عمليّة أخرى) تبقى
    تحمل الطبقة القديمة؛ هذا النشر يُخليها فوراً. يُعيد النتيجة ولا يرمي (P3-INV): كان فشلُ
    النشر يُبتلَع والصفُّ يُعَدّ منجَزاً، فتبقى عمليّةٌ تُخدِّم الهندسةَ القديمة بلا أثر.
    ``not_configured``: لا ``REDIS_URL`` ⇒ لا قناةَ إخلاءٍ في هذا النشر أصلاً (ليس فشلاً)؛
    ``not_delivered``: القناةُ مُهيّأة والنشرُ فشل (اتّصال/حزمة) ⇒ يُعيده المُستدعي."""
    global _redis_pub
    url = os.getenv("REDIS_URL")
    if not url:
        return LAYER_EVICT_NOT_CONFIGURED
    if not field_id:
        return LAYER_EVICT_NOT_DELIVERED
    try:
        if _redis_pub is None:
            import redis.asyncio as _aioredis

            _redis_pub = _aioredis.from_url(url, encoding="utf-8", decode_responses=True)
        await _redis_pub.publish(LAYER_EVICT_CHANNEL, field_id)
    except Exception as e:  # noqa: BLE001 — يُسجَّل ويُعاد لا يُبتلَع (القرار للمُستدعي)
        logger.warning("layer-evict publish failed (field=%s): %s", field_id, e)
        return LAYER_EVICT_NOT_DELIVERED
    return LAYER_EVICT_DELIVERED


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


def _json_object(value: Any) -> dict:
    """asyncpg يُعيد ``metadata`` نصّاً ما لم يُسجَّل codec؛ الوهميُّ يُعيده قاموساً."""
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _parse_instant(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    # لحظةٌ بلا منطقة زمنيّة لا تُقارَن بعمود ``timestamptz`` دون تخمين — تُرفَض لا تُخمَّن.
    return parsed if parsed.tzinfo is not None else None


def invalidation_scope(row: Any) -> tuple[int | None, datetime | None]:
    """``(المراجعة المُسمّاة، لحظة التغيير)`` لصفّ إبطال — ما يحدّد «الأصول السابقة».

    المراجعةُ من ``metadata.geometry_revision`` (عددٌ موجب، لا ``bool``). واللحظةُ من
    ``metadata.geometry_changed_at`` التي تكتبها المنصّةُ بساعة القاعدة داخل معاملة الحقل؛
    وغيابُها (نيّةٌ أقدم من هذا العقد) ⇒ ``created_at`` صفِّ الطابور: وصولُ الأمر إلى المالك،
    وهو **بعد** الالتزام دائماً — أوسعُ من الصحيح لكنّه لا يَسِم ما يُنتَج بعد الوصول.
    """
    meta = _json_object(row.get("metadata"))
    rev = meta.get("geometry_revision")
    revision = rev if isinstance(rev, int) and not isinstance(rev, bool) and rev > 0 else None
    changed_at = _parse_instant(meta.get("geometry_changed_at"))
    if changed_at is None:
        changed_at = _parse_instant(row.get("created_at"))
    return revision, changed_at


def claim_attempts(row: Any) -> int:
    """عددُ المطالبات السابقة للصفّ (``metadata.claim_attempts``)؛ غيرُ الصالح ⇒ صفر.

    مرآةُ حارس الزيادة في عبارة المطالبة حرفيّاً (عددٌ صحيح من ١ إلى ٩ أرقام): رقمُ المحاولة
    هنا هو سياجُ الإجارة في SQL، فاختلافُهما يُفشل إنهاءَ صفٍّ سليم."""
    n = _json_object(row.get("metadata")).get("claim_attempts")
    ok = isinstance(n, int) and not isinstance(n, bool) and 0 < n <= 999_999_999
    return n if ok else 0


# C1: المطالَبُ = المعلّقُ الذي انقضت مهلةُ إعادته + الـ``processing`` الذي انقضت إجارتُه
# (أو بلا إجارة: صفٌّ طالبه إصدارٌ سابق بلا إجارات فعلق). الإجارةُ الحيّة لا تُسرَق.
# وصبُّ ``metadata`` محروسٌ بالنوع داخل ``CASE`` (الترتيبُ فيه مضمون، بخلاف ``AND``/``OR``):
# صفٌّ واحد بقيمةٍ غير صالحة كان يُلغي معاملةَ المطالبة كلَّ دورة ⇒ طابورٌ واقف للجميع.
# غيرُ الصالح يُقرأ غائباً: مهلةٌ ⇒ مستحقّة، إجارةٌ ⇒ منقضية (الإعادةُ idempotent).
_CLAIM_SQL = """
    SELECT id, tenant_id, field_id, reason, metadata, created_at
    FROM raster_cache_invalidations
    WHERE (status = 'pending'
           AND CASE WHEN jsonb_typeof(metadata->'retry_after') = 'number'
                    THEN (metadata->>'retry_after')::numeric <= extract(epoch from now())
                    ELSE true END)
       OR (status = 'processing'
           AND CASE WHEN jsonb_typeof(metadata->'lease_until') = 'number'
                    THEN (metadata->>'lease_until')::numeric <= extract(epoch from now())
                    ELSE true END)
    ORDER BY created_at
    LIMIT $1
    FOR UPDATE SKIP LOCKED
"""


async def run_once(pool: asyncpg.Pool, *, batch_size: int = 50) -> int:
    """يعالج دفعة من الإبطالات المعلّقة. يُرجِع عدد الصفوف المُنجَزة (processed).

    لا يُعَدّ صفٌّ لم يُسلَّم إخلاءُ ذاكرته (يُحرَّر لإعادة المحاولة)، ولا صفٌّ استنفد
    محاولاته (يُنهى failed)."""
    # كلُّ إنهاءٍ مشروطٌ بأنّ الإجارة ما زالت لهذه المطالبة (رقمُ المحاولة رمزُها:
    # ``status='processing' AND claim_attempts = $2``): عاملٌ بطيءٌ استُعيدت مطالبتُه لا يكتب
    # فوق حالة من استعادها، ولا يَعُدّ صفّاً لم يُنهِه هو.
    async with pool.acquire() as conn:
        # المطالبة الذرّيّة: SELECT ... FOR UPDATE SKIP LOCKED ثمّ وسم processing بإجارة
        # داخل معاملة واحدة — فلا يلتقط عاملان الصفّ نفسه (القفل يُحرَّر بعد الوسم، والإجارة
        # تحمي الصفّ بعده إلى أن تنقضي).
        async with conn.transaction():
            candidates = await conn.fetch(_CLAIM_SQL, batch_size)
            exhausted = [r for r in candidates if claim_attempts(r) >= MAX_CLAIM_ATTEMPTS]
            rows = [r for r in candidates if claim_attempts(r) < MAX_CLAIM_ATTEMPTS]
            if exhausted:
                await conn.execute(
                    "UPDATE raster_cache_invalidations SET status='failed', processed_at=now(), "
                    "metadata = (metadata - 'lease_until' - 'retry_after') "
                    "|| jsonb_build_object('last_error', 'claim attempts exhausted') "
                    "WHERE id = ANY($1::bigint[])",
                    [r["id"] for r in exhausted],
                )
            if rows:
                await conn.execute(
                    "UPDATE raster_cache_invalidations SET status='processing', "
                    "metadata = (metadata - 'retry_after') || jsonb_build_object("
                    "'lease_until', extract(epoch from now() + make_interval(secs => $2)), "
                    "'claim_attempts', CASE WHEN jsonb_typeof(metadata->'claim_attempts') = "
                    "'number' AND metadata->>'claim_attempts' ~ '^[0-9]{1,9}$' "
                    "THEN (metadata->>'claim_attempts')::int ELSE 0 END + 1) "
                    "WHERE id = ANY($1::bigint[])",
                    [r["id"] for r in rows],
                    CLAIM_LEASE_SECONDS,
                )
        for r in exhausted:
            logger.warning(
                "invalidation failed id=%s field=%s: claim attempts exhausted (%s)",
                r["id"],
                r["field_id"],
                claim_attempts(r),
            )
        processed = 0
        for row in rows:
            rid = row["id"]
            tenant = str(row["tenant_id"]) if row["tenant_id"] else None
            field = row["field_id"]
            attempt = claim_attempts(row) + 1
            try:
                revision, changed_at = invalidation_scope(row)
                deleted = tile_cache_maint.invalidate_field_tile_cache(tenant, field)
                # v10-F6: set_config(...,true) عابرٌ للمعاملة — نُغلّف الضبط + التحديثات
                # المُعتمدة على المستأجِر في معاملة واحدة كي يبقى app.current_tenant سارياً
                # (يهمّ عند السقوط إلى DATABASE_URL بدور مقيّد بلا BYPASSRLS).
                async with conn.transaction():
                    await _set_tenant(conn, tenant)
                    # الأصولُ **السابقة للتغيير المُسمّى** وحدَها. المقيس حيّاً على مكدّس
                    # docker-compose.v9.yml (2026-09-29): إبطالُ ``field.created`` كان يصل بعد
                    # أن تصير صورُ Sentinel-2 المُطلَقة بعد الالتزام ``ready``، فيَسِمها هذا
                    # العامل ``stale`` بعد ~ثانيتين من الإنشاء، ومصغّراتُها (``ready`` حصراً)
                    # تعود 404. حقلٌ جديد لا أصولَ سابقةً له، فلا هدفَ لإبطاله. المراجعةُ
                    # المعروفة تُقارَن بالمُسمّاة (v143: «نَسَب الهندسة… للإبطال»)، والمجهولةُ
                    # بلحظة التغيير؛ ولا مسمّى ولا لحظة ⇒ السلوكُ السابق (كلُّ جاهز).
                    staled = await conn.execute(
                        "UPDATE raster_assets SET asset_status='stale' "
                        "WHERE tenant_id = $1::uuid AND field_id = $2 AND asset_status = 'ready' "
                        "AND CASE WHEN $3::int IS NOT NULL AND geometry_revision IS NOT NULL "
                        "THEN geometry_revision < $3::int "
                        "ELSE $4::timestamptz IS NULL OR created_at IS NULL "
                        "OR created_at < $4::timestamptz END",
                        tenant,
                        field,
                        revision,
                        changed_at,
                    )
                # v11-F3/F5: أبلِغ عمليّة raster-service لتُخلي طبقات الحقل من الذاكرة
                # (بعد نجاح إبطال القرص+DB) — خارج المعاملة. P3-INV: الإنجازُ بعد النشر لا
                # قبله؛ نشرٌ فاشل يُحرِّر الصفّ ``pending`` بمهلة (الإعادةُ تُكرِّر الحذفَ والوسمَ
                # idempotent ثمّ تنشر)، ومستنفِدُ المحاولات يُنهى ``failed`` عند المطالبة التالية.
                evict = await _publish_layer_evict(field)
                if evict == LAYER_EVICT_NOT_DELIVERED:
                    await conn.execute(
                        "UPDATE raster_cache_invalidations SET status='pending', "
                        "metadata = (metadata - 'lease_until') || jsonb_build_object("
                        "'layer_evict', 'not_delivered', "
                        "'retry_after', extract(epoch from now() + make_interval(secs => $3))) "
                        "WHERE id=$1 AND status='processing' "
                        "AND metadata->'claim_attempts' = to_jsonb($2::int)",
                        rid,
                        attempt,
                        RETRY_BACKOFF_SECONDS * attempt,
                    )
                    logger.warning(
                        "invalidation not completed id=%s field=%s: layer-evict not delivered "
                        "(attempt %s/%s; retried after backoff)",
                        rid,
                        field,
                        attempt,
                        MAX_CLAIM_ATTEMPTS,
                    )
                    continue
                done = await conn.execute(
                    "UPDATE raster_cache_invalidations "
                    "SET status='processed', processed_at=now(), "
                    "metadata = (metadata - 'lease_until' - 'retry_after') "
                    "|| jsonb_build_object('layer_evict', $3::text) "
                    "WHERE id=$1 AND status='processing' "
                    "AND metadata->'claim_attempts' = to_jsonb($2::int)",
                    rid,
                    attempt,
                    evict,
                )
                if done != "UPDATE 1":
                    logger.warning(
                        "invalidation id=%s field=%s: lease lost before completion (attempt %s)",
                        rid,
                        field,
                        attempt,
                    )
                    continue
                processed += 1
                logger.info(
                    "invalidation processed id=%s field=%s tiles_deleted=%s assets=%s reason=%s "
                    "prior_to_revision=%s prior_to=%s layer_evict=%s",
                    rid,
                    field,
                    deleted,
                    staled,
                    row["reason"],
                    revision,
                    changed_at.isoformat() if changed_at else None,
                    evict,
                )
            except Exception as e:  # noqa: BLE001 — صفّ واحد فاشل لا يُسقط الدفعة
                try:
                    await conn.execute(
                        "UPDATE raster_cache_invalidations "
                        "SET status='failed', processed_at=now(), "
                        "metadata = metadata - 'lease_until' "
                        "WHERE id=$1 AND status='processing' "
                        "AND metadata->'claim_attempts' = to_jsonb($2::int)",
                        rid,
                        attempt,
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
