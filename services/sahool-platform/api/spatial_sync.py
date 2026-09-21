"""Spatial synchronization helpers for geometry history and raster invalidation."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("sahool.spatial_sync")

#: نوعُ المهمّة في ``processing_jobs`` (مملوكٌ للمنصّة) الذي يحمل نيّةَ إبطال كاش الراستر.
RASTER_INVALIDATION_JOB_TYPE = "raster.cache_invalidation"

# المحارفُ التي يقبلها raster-service في مفتاح الطلب (routers/registry_writes.py).
_REQUEST_ID_UNSAFE = re.compile(r"[^A-Za-z0-9._:-]+")
_REQUEST_ID_MAX = 128


async def save_field_geometry_revision(
    conn,
    *,
    tenant_id: str,
    field_id: str,
    geometry: dict[str, Any],
    changed_by: str | None,
    reason: str,
    source: str,
    metadata: dict[str, Any] | None = None,
) -> int | None:
    """Append a field geometry revision. Safe no-op if migration was not applied yet."""
    try:
        rev = await conn.fetchval(
            """
            INSERT INTO field_geometry_history
                (tenant_id, field_id, geometry, changed_by, reason, source, metadata)
            VALUES ($1::uuid, $2, $3::jsonb, $4, $5, $6, $7::jsonb)
            RETURNING revision
            """,
            tenant_id,
            field_id,
            json.dumps(geometry),
            changed_by,
            reason,
            source,
            json.dumps(metadata or {}),
        )
        return int(rev) if rev is not None else None
    except Exception:  # noqa: BLE001 — أفضل-جهد: سجلّ المراجعة لا يجب أن يكسر حفظ الحقل (جدول v96 قد لا يكون مُطبَّقاً بعد)
        return None


def invalidation_request_id(
    *, field_id: str, reason: str, metadata: dict[str, Any] | None = None
) -> str:
    """مفتاحُ idempotency لأمر الإبطال — حتميٌّ متى عُرفت مراجعةُ الهندسة.

    ``(reason, field_id, geometry_revision)`` يسمّي تغييراً واحداً بعينه: إعادةُ إرسال
    الأمر نفسِه (مهلة، إعادةُ محاولة) تُطابق الصفَّ القائم في raster-service ولا تُدرج
    ثانياً، ومراجعةٌ هندسيّة ثانية مفتاحٌ ثانٍ لا تكرارٌ للأولى. بلا مراجعةٍ (سجلُّ
    المراجعات لم يُكتب — جدول v96 غائب) لا هويّةَ للتغيير، فيُولَّد مفتاحٌ عشوائيّ ويُعلَن
    ذلك بالاسم (``norev``) بدل ادّعاء حتميّةٍ ليست هناك.
    """
    rev = (metadata or {}).get("geometry_revision")
    if isinstance(rev, int) and not isinstance(rev, bool):
        raw = f"{reason}:{field_id}:rev{rev}"
    else:
        raw = f"{reason}:{field_id}:norev-{uuid.uuid4().hex}"
    safe = _REQUEST_ID_UNSAFE.sub("-", raw).strip("-._:") or "invalidation"
    return safe[:_REQUEST_ID_MAX]


async def mark_raster_cache_stale(
    conn, *, tenant_id: str, field_id: str, reason: str, metadata: dict[str, Any] | None = None
) -> int | None:
    """Record a durable raster-invalidation **intent** on the caller's transaction (D1).

    ``raster_cache_invalidations`` is owned by raster-service; the platform no longer
    writes it. What the platform owns is the *intent*: a ``processing_jobs`` row
    (``job_type = raster.cache_invalidation``, platform-owned by contract) written on the
    same connection — and therefore in the same transaction — as the field write. A
    rollback drops the intent with the field change; a commit makes it durable. No HTTP
    happens here: delivery to raster-service's owned command
    (``POST /v1/fields/{field_id}/cache-invalidations``) is done **after COMMIT** by
    the dispatcher section of this module (``run_once``), which retries with the same deterministic
    ``request_id`` and marks the intent completed only on the owner's acknowledgement.

    Best-effort, as the old insert was: the intent write runs inside a savepoint, so a
    failure neither aborts the enclosing transaction nor breaks the field save — it is
    logged with the field and request id so the loss is visible. Returns the intent's
    job id (existing one when the same request id is already recorded in this tenant).
    """
    request_id = invalidation_request_id(field_id=field_id, reason=reason, metadata=metadata)
    params = {"request_id": request_id, "reason": reason, "metadata": dict(metadata or {})}
    try:
        async with conn.transaction():  # savepoint داخل معاملة المُستدعي
            existing = await conn.fetchval(
                """
                SELECT id FROM processing_jobs
                WHERE tenant_id = $1::uuid AND field_id = $2 AND job_type = $3
                  AND parameters->>'request_id' = $4
                ORDER BY id
                LIMIT 1
                """,
                tenant_id,
                field_id,
                RASTER_INVALIDATION_JOB_TYPE,
                request_id,
            )
            if existing is not None:
                return int(existing)
            job_id = await conn.fetchval(
                """
                INSERT INTO processing_jobs
                    (tenant_id, field_id, job_type, status, priority, parameters, result)
                VALUES ($1::uuid, $2, $3, 'pending', 3, $4::jsonb, '{}'::jsonb)
                RETURNING id
                """,
                tenant_id,
                field_id,
                RASTER_INVALIDATION_JOB_TYPE,
                json.dumps(params),
            )
            return int(job_id) if job_id is not None else None
    except Exception as exc:  # noqa: BLE001 — أفضل-جهد: نيّةُ الإبطال لا تكسر حفظَ الحقل
        logger.warning(
            "raster cache invalidation intent not recorded field=%s request=%s: %s",
            field_id,
            request_id,
            exc,
        )
        return None


# ═══ التسليمُ بعد الالتزام — المُوصِّل (D1) ═══════════════════════════════════════
#
# النيّةُ أعلاه نصفُ العقد؛ هذا نصفُه الآخر: بعد COMMIT يطالب المُوصِّلُ النيّاتِ
# المستحقّة بإجارة، يُرسل كلَّ نيّة إلى أمر raster-service المملوك
# (``POST /v1/fields/{field_id}/cache-invalidations`` عبر ``api.raster_service_client``)،
# ولا يَسِمها ``completed`` إلّا بإقرار المالك. فشلُ التسليم يُعيدها ``pending`` بمهلةٍ
# متزايدة والمفتاحِ نفسِه (raster-service يُزيل التكرار، فضياعُ الردّ لا يُدرج ثانياً)؛
# ورفضٌ لا تغيّره إعادةُ المحاولة (توكن/مستأجِر/أمرٌ غيرُ صالح) ينتهي ``failed`` بسببه في
# ``error_msg`` — مرئيّاً للمُشغِّل لا صامتاً.
#
# لماذا هنا لا في وحدةٍ جديدة: ميزانيّةُ وحدات المنصّة مجمَّدة
# (``platform_python_module_baseline.json``)، وهذه الوحدةُ هي «تزامنُ الهندسة وإبطالُ
# الراستر» أصلاً. ولماذا ``processing_jobs`` لا جدولٌ جديد: مملوكٌ للمنصّة بالعقد ويحمل
# إجاراتِ JSON على سابقة ``PlatformBootstrapStore`` — فلا هجرةَ ولا تفويضَ مسارٍ مجمَّد.
# ولماذا مهمّةُ مُجدوِل لا خدمةُ compose: ``api/main.py`` على سقف أسطره، والمنصّةُ تُدير
# كنسَها الدوريّ داخل العمليّة (``api.scheduler``) تحت ``cluster_singleton`` فتُنفَّذ بنسخةٍ
# واحدة لكلّ تكّة. التسليمُ يقرأ النيّاتِ عبر المستأجرين فيحتاج مسبحَ الوظائف
# (``JOBS_DATABASE_URL``)؛ على مسبح التطبيق وحدَه يُخفي عزلُ الصفوف كلَّ شيء فلا يُطالَب
# شيء — مُعلَنٌ لا مخفيّ. العميلُ يُستورَد كسولاً داخل ``run_once`` فقط: لا HTTP في متناول
# ``mark_raster_cache_stale``.

TASK_NAME = "raster_invalidation_dispatch"
LEASE_SECONDS = 120.0
MAX_ATTEMPTS = 8
#: back-off بعد المحاولة n (ثوانٍ) — الأخيرةُ تتكرّر حتّى نفاد المحاولات.
BACKOFF_SECONDS = (5, 15, 60, 300, 900, 1800, 3600, 7200)
#: رفضٌ لا تغيّره إعادةُ المحاولة: توكن/مستأجِر/أمرٌ غيرُ صالح. 404 **ليس** منها — كاشُ
#: مالك الحقل السالب في raster-service (15ث) قد يسبق رؤيةَ حقلٍ التُزم للتوّ.
PERMANENT_STATUSES = frozenset({400, 401, 403, 422})

SendFn = Callable[..., Awaitable[dict[str, Any]]]


def backoff_seconds(attempt: int) -> int:
    """ثوانٍ قبل المحاولة التالية بعد ``attempt`` محاولاتٍ فاشلة (تبدأ من 1)."""
    return BACKOFF_SECONDS[min(max(attempt, 1), len(BACKOFF_SECONDS)) - 1]


def _jsonish(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _rows_touched(result: Any) -> int:
    try:
        return int(str(result).rsplit(" ", 1)[-1])
    except (TypeError, ValueError):
        return 0


async def claim_due(conn: Any, *, limit: int = 25) -> list[dict[str, Any]]:
    """يُطالِب دفعةً من النيّات المستحقّة ويُؤجّرها — عبارةٌ واحدة، ``FOR UPDATE SKIP LOCKED``.

    مستحقّة = ``pending`` بلا إجارةٍ حيّة وبلا ``next_attempt_at`` في المستقبل. تُوسَم
    ``running`` بإجارةٍ ذات رمزٍ ومهلة؛ الإنهاءُ لاحقاً CAS على الرمز، فلا يكتب عاملٌ
    انتهت إجارتُه فوق عمل من أعاد المطالبة.
    """
    rows = await conn.fetch(
        """
        WITH due AS (
            SELECT id FROM processing_jobs
            WHERE job_type = $1 AND status = 'pending'
              AND (result->'lease' IS NULL OR result->'lease' = 'null'::jsonb
                   OR (result->'lease'->>'expires_at')::timestamptz <= clock_timestamp())
              AND (result->>'next_attempt_at' IS NULL
                   OR (result->>'next_attempt_at')::timestamptz <= clock_timestamp())
            ORDER BY priority, id
            LIMIT $2
            FOR UPDATE SKIP LOCKED
        )
        UPDATE processing_jobs AS j
        SET status = 'running',
            started_at = COALESCE(j.started_at, clock_timestamp()),
            updated_at = clock_timestamp(),
            result = COALESCE(j.result, '{}'::jsonb) || jsonb_build_object(
                'lease', jsonb_build_object(
                    'token', gen_random_uuid()::text,
                    'expires_at', (clock_timestamp() + make_interval(secs => $3))::text))
        FROM due
        WHERE j.id = due.id
        RETURNING j.id, j.tenant_id::text AS tenant_id, j.field_id,
                  j.parameters::text AS parameters, j.result::text AS result
        """,
        RASTER_INVALIDATION_JOB_TYPE,
        int(limit),
        float(LEASE_SECONDS),
    )
    return [dict(r) for r in rows]


async def deliver(conn: Any, job: dict[str, Any], *, send: SendFn) -> str:
    """يُسلّم نيّةً واحدة ويُنهيها بـCAS على رمز الإجارة.

    يُعيد ``delivered`` · ``retry`` · ``failed`` · ``lease_lost``. النجاحُ وحدَه يُكمِل
    الصفّ ويحفظ إقرارَ المالك (``ack``) فيه؛ ``deduplicated`` في الإقرار يعني أنّ محاولةً
    سابقة وصلت وضاع ردُّها — لا أثرَ مكرَّراً في طابور المالك.
    """
    params = _jsonish(job.get("parameters")) or {}
    result = _jsonish(job.get("result")) or {}
    token = (result.get("lease") or {}).get("token") if isinstance(result, dict) else None
    attempts = int(result.get("attempts") or 0) if isinstance(result, dict) else 0
    request_id = params.get("request_id")
    if not request_id:
        return await _finish(
            conn,
            job,
            token,
            status="failed",
            attempts=attempts + 1,
            error="intent without request_id",
        )
    try:
        ack = await send(
            job["field_id"],
            tenant_id=job["tenant_id"],
            reason=params.get("reason") or "field.geometry.updated",
            request_id=request_id,
            metadata=params.get("metadata") or {},
        )
    except Exception as exc:  # noqa: BLE001 — كلُّ فشلٍ يُصنَّف: دائمٌ أو يُعاد
        status_code = getattr(exc, "status_code", None)
        attempts += 1
        permanent = status_code in PERMANENT_STATUSES or attempts >= MAX_ATTEMPTS
        message = f"{type(exc).__name__}: {getattr(exc, 'detail', None) or exc}"[:500]
        if permanent:
            return await _finish(
                conn, job, token, status="failed", attempts=attempts, error=message
            )
        return await _finish(
            conn,
            job,
            token,
            status="pending",
            attempts=attempts,
            error=message,
            retry_in=backoff_seconds(attempts),
        )
    return await _finish(conn, job, token, status="completed", attempts=attempts + 1, ack=ack)


async def _finish(
    conn: Any,
    job: dict[str, Any],
    token: str | None,
    *,
    status: str,
    attempts: int,
    error: str | None = None,
    retry_in: int | None = None,
    ack: dict[str, Any] | None = None,
) -> str:
    patch: dict[str, Any] = {"attempts": attempts}
    if error is not None:
        patch["last_error"] = error
    if ack is not None:
        patch["ack"] = ack
    outcome = {"completed": "delivered", "pending": "retry", "failed": "failed"}[status]
    touched = await conn.execute(
        """
        UPDATE processing_jobs
        SET status = $4,
            updated_at = clock_timestamp(),
            progress = CASE WHEN $4 = 'completed' THEN 100 ELSE progress END,
            finished_at = CASE WHEN $4 IN ('completed', 'failed') THEN clock_timestamp() ELSE NULL END,
            error_msg = $6,
            result = (COALESCE(result, '{}'::jsonb) - 'lease' - 'next_attempt_at') || $5::jsonb
                     || CASE WHEN $7::float8 IS NULL THEN '{}'::jsonb
                        ELSE jsonb_build_object(
                            'next_attempt_at',
                            (clock_timestamp() + make_interval(secs => $7))::text) END
        WHERE id = $1 AND job_type = $2 AND result->'lease'->>'token' = $3
        """,
        job["id"],
        RASTER_INVALIDATION_JOB_TYPE,
        token or "",
        status,
        json.dumps(patch, default=str),
        error,
        float(retry_in) if retry_in is not None else None,
    )
    if _rows_touched(touched) == 0:
        return "lease_lost"
    return outcome


async def run_once(
    pool: Any, *, batch_size: int = 25, send: SendFn | None = None
) -> dict[str, int]:
    """دورةٌ واحدة: مطالبةٌ مُلتزَمة (TX-1) ثمّ تسليمٌ خارج أيّ معاملة ثمّ إنهاءٌ بـCAS (TX-2)."""
    if send is None:
        from api.raster_service_client import enqueue_raster_cache_invalidation

        send = enqueue_raster_cache_invalidation
    counts = {"claimed": 0, "delivered": 0, "retry": 0, "failed": 0, "lease_lost": 0}
    async with pool.acquire() as conn:
        async with conn.transaction():
            jobs = await claim_due(conn, limit=batch_size)
        for job in jobs:
            counts["claimed"] += 1
            outcome = await deliver(conn, job, send=send)
            counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def dispatch_interval_seconds() -> float:
    return float(os.getenv("RASTER_INVALIDATION_DISPATCH_SECONDS", "15"))


def _platform_jobs_pool() -> Any:
    """مسبحُ الوظائف (دورٌ يتجاوز عزلَ الصفوف) وإلّا مسبحُ التطبيق — يُقرأ عند كلّ تكّة لا عند التسجيل."""
    from api import main as platform_main

    return platform_main._JOBS_POOL or platform_main._DB_POOL


def register_dispatch_task(scheduler: Any, cluster_singleton: Any, *, pool_getter=None) -> None:
    """يُسجّل مهمّةَ التسليم في مُجدوِل المنصّة (نسخةٌ واحدة لكلّ تكّة)."""
    getter = pool_getter or _platform_jobs_pool

    async def _sweep() -> None:
        pool = getter()
        if pool is None:
            return
        counts = await run_once(pool)
        if counts["claimed"]:
            logger.info("raster invalidation dispatch: %s", counts)

    scheduler.register(
        TASK_NAME,
        dispatch_interval_seconds(),
        cluster_singleton(_sweep, task_name=TASK_NAME, pool_getter=getter),
    )
