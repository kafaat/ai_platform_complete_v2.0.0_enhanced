"""offline_pending_db — طابور العمليّات المعلّقة الدائم (Postgres-backed).

النواة ‎sahool_core.offline_first‎ نقيّة (لا I/O): تُدير الـqueue في الذاكرة،
فتضيع العمليّات المعلّقة عند إعادة تشغيل العمليّة (process restart). هذا الملف
يُضيف طبقة **إدامة** للعمليّات قبل مزامنتها: تُكتَب فور تسجيلها offline في جدول
‎offline_pending_ops‎ (status='pending')، فتنجو من إعادة التشغيل، ثمّ تُعلَّم
‎processed‎ بعد نجاح المزامنة (تمييزاً عن ‎offline_synced_operations‎ الذي يُدوّن
ما اكتملت مزامنته فقط).

التصميم (مطابق لـ‎offline_sync_db.py‎):
  • دوالّ async تعمل على ``conn`` جاهز (من ``tenant_connection``) ضمن سياق RLS
    الذي يضبطه المستدعي — لا تفتح pool بنفسها، فالاختبار بسيط (fake conn).
  • idempotent على ``op_id`` (ON CONFLICT DO NOTHING) ⇒ إعادة الإدخال لا تُكرّر.
  • fail-safe: المستدعي يبتلع الاستثناء ويبقى على المسار الذاكريّ (in-memory)
    حين لا قاعدة (DATABASE_URL غير مضبوط) ⇒ اختبارات الوحدة بلا قاعدة تبقى خضراء.

العزل: RLS على ``tenant_id`` عبر ‎_sahool_apply_tenant_rls‎ (migration v91).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - نوعيّ فقط
    import asyncpg
    from core.offline_first import PendingOperation


def _default_max_attempts() -> int:
    """أقصى عدد محاولات مزامنة قبل الانتقال النهائيّ إلى ``failed`` (poison guard).

    قابل للضبط عبر ``OFFLINE_PENDING_MAX_ATTEMPTS`` (إغلاق مرن)؛ الافتراضيّ 5 —
    قيمة معتدلة تعطي هامشاً لأعطال عابرة (شبكة/قاعدة) دون ترك عمليّة سامّة تدور
    إلى الأبد. قيمة غير صالحة/≤0 ⇒ ارتداد آمن للافتراضيّ.
    """
    raw = os.getenv("OFFLINE_PENDING_MAX_ATTEMPTS", "").strip()
    if raw:
        try:
            parsed = int(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return 5


MAX_ATTEMPTS = _default_max_attempts()


def should_fail(attempts: int, max_attempts: int = MAX_ATTEMPTS) -> bool:
    """هل تنتقل عمليّة إلى ``failed`` النهائيّة بعد هذه المحاولة الفاشلة؟

    منطق نقيّ (بلا I/O) قابل لاختبار الوحدة: ``attempts`` هو العدّاد **قبل** زيادة
    هذه المحاولة؛ بعد الزيادة يصبح ``attempts + 1``، فإن بلغ الحدّ ``max_attempts``
    استُنفدت المحاولات ⇒ ``failed``. أرقام حدّيّة (≤0) تُعامَل كحدّ 1 (أوّل فشل نهائيّ)
    تفادياً لحلقة لا نهائيّة على ضبط خاطئ.
    """
    limit = max_attempts if max_attempts > 0 else 1
    return (attempts + 1) >= limit


def _parse_ts(value: object) -> datetime:
    """يحوّل ISO string إلى datetime واعٍ بـUTC لعمود timestamptz (NOT NULL).

    offline_first يُنتج created_at عبر ``datetime.utcnow().isoformat()`` (naive)؛
    نعتبره UTC صراحةً. ندعم اللاحقة 'Z'، ونرجع الآن (UTC) كقيمة آمنة بدل None
    حتّى لا يفشل الإدراج بسبب فرق تنسيق طفيف (نفس منطق offline_sync_db).
    """
    dt: datetime | None = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            dt = None
    if dt is None:
        dt = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _kind_value(kind: object) -> str:
    """يستخرج القيمة النصّيّة لـOperationKind (أو يقبل نصّاً جاهزاً)."""
    return kind.value if hasattr(kind, "value") else str(kind)


async def enqueue_pending(
    conn: asyncpg.Connection, *, op: PendingOperation, tenant_id: str
) -> bool:
    """يُدِيم عمليّة معلّقة في ``offline_pending_ops`` (idempotent على op_id).

    يجب أن يكون ``conn`` ضمن سياق المستأجر (tenant_connection) ليُطبَّق RLS.
    يرفع استثناء عند خطأ قاعدة فعلي (يُترك للمستدعي ليرتدّ للمسار الذاكريّ).

    Returns
    -------
    bool
        True إن أُدرجت أو كانت موجودة سلفاً (ON CONFLICT DO NOTHING ⇒ لا تكرار).
    """
    await conn.execute(
        """
        INSERT INTO offline_pending_ops
            (op_id, tenant_id, user_id, op_kind, payload, status,
             created_at, attempts)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5::jsonb, 'pending', $6, 0)
        ON CONFLICT (op_id) DO NOTHING
        """,
        op.op_id,
        tenant_id,
        str(op.user_id),
        _kind_value(op.kind),
        json.dumps(op.payload or {}),
        _parse_ts(op.created_at),
    )
    return True


async def fetch_pending(conn: asyncpg.Connection, *, limit: int = 100) -> list[dict]:
    """يقرأ العمليّات المعلّقة (status='pending') للمستأجر الحالي بترتيب FIFO.

    RLS يُرشّح حسب ``app.current_tenant`` تلقائيّاً. يُرجع dicts خفيفة ليُعاد
    بناء ``PendingOperation`` منها عند الإقلاع (استرداد الطابور بعد restart).
    """
    rows = await conn.fetch(
        """
        SELECT op_id, tenant_id, user_id, op_kind, payload,
               created_at, attempts, last_error
        FROM offline_pending_ops
        WHERE status = 'pending'
        ORDER BY created_at ASC
        LIMIT $1
        """,
        limit,
    )
    out: list[dict] = []
    for r in rows:
        payload = r["payload"]
        out.append(
            {
                "op_id": str(r["op_id"]),
                "tenant_id": str(r["tenant_id"]),
                "user_id": r["user_id"],
                "op_kind": r["op_kind"],
                "payload": payload if isinstance(payload, dict) else json.loads(payload),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "attempts": r["attempts"],
                "last_error": r["last_error"],
            }
        )
    return out


async def claim_pending(conn: asyncpg.Connection, *, op_id: str) -> bool:
    """يُطالِب عمليّة ``pending`` بنقلها ذرّيّاً إلى ``processing`` (single-claimer).

    ``UPDATE … WHERE status='pending' RETURNING`` ذرّيّ: عامل واحد فقط يفوز بالصفّ
    (الثاني يجد الحالة ``processing`` فلا يُطابق شرطه ⇒ لا صفّ راجع) — يمنع
    التنفيذ المزدوج للأثر الجانبيّ عند تزامن عاملَين على المزامنة نفسها.

    Returns
    -------
    bool
        ``True`` إن فاز هذا المستدعي بالمطالبة (نُقل الصفّ pending→processing)؛
        ``False`` إن كان الصفّ غير معلَّق (مُطالَب سلفاً/مُنجَز/فاشل/غير موجود).
    """
    row = await conn.fetchrow(
        """
        UPDATE offline_pending_ops
        SET status = 'processing'
        WHERE op_id = $1::uuid AND status = 'pending'
        RETURNING op_id
        """,
        op_id,
    )
    return row is not None


async def mark_processed(conn: asyncpg.Connection, *, op_id: str) -> bool:
    """يُعلِّم عمليّة ``processed`` بعد نجاح مزامنتها (idempotent).

    يقبل الصفّ في ``pending`` (لم يُطالَب) أو ``processing`` (مُطالَب) ⇒ يعمل سواء
    مرّ العامل بمرحلة المطالبة أم لا (توافق خلفيّ). لا يلمس صفّاً نهائيّاً
    (``processed``/``failed``) ⇒ إعادة الاستدعاء لا تُغيّر ``processed_at`` ثانيةً.
    """
    await conn.execute(
        """
        UPDATE offline_pending_ops
        SET status = 'processed', processed_at = NOW()
        WHERE op_id = $1::uuid AND status IN ('pending', 'processing')
        """,
        op_id,
    )
    return True


async def mark_failed(
    conn: asyncpg.Connection,
    *,
    op_id: str,
    error: str,
    max_attempts: int = MAX_ATTEMPTS,
) -> bool:
    """يزيد عدّاد المحاولات ويُدوّن آخر خطأ؛ عند استنفاد المحاولات ⇒ ``failed``.

    poison guard: كانت العمليّة تبقى ``pending`` أبداً فتدور بلا نهاية على فشل
    دائم؛ الآن حين ``attempts + 1 >= max_attempts`` تنتقل إلى ``failed`` النهائيّة
    (مع ``failed_at``) فتُنهي الحلقة. الفشل القابل لإعادة المحاولة (لم يبلغ الحدّ)
    يعود إلى ``pending`` (سواء أُطالِب الصفّ ⇒ ``processing`` أم لا) ليُعاد لاحقاً.

    يعمل على الصفّ في ``pending`` أو ``processing`` (توافق خلفيّ + مسار المطالبة).
    الحساب داخل SQL ذرّيّ (لا سباق قراءة-ثمّ-كتابة). idempotent على الحالات
    النهائيّة (لا يُطابق شرط ``IN ('pending','processing')``).
    """
    await conn.execute(
        """
        UPDATE offline_pending_ops
        SET attempts = attempts + 1,
            last_error = $2,
            status = CASE WHEN attempts + 1 >= $3 THEN 'failed' ELSE 'pending' END,
            failed_at = CASE WHEN attempts + 1 >= $3 THEN NOW() ELSE failed_at END
        WHERE op_id = $1::uuid AND status IN ('pending', 'processing')
        """,
        op_id,
        (error or "")[:500],
        max_attempts if max_attempts > 0 else 1,
    )
    return True


async def reclaim_stuck_processing(
    conn: asyncpg.Connection, *, older_than_minutes: int = 30
) -> int:
    """يُعيد الصفوف العالقة في ``processing`` إلى ``pending`` (استرداد بعد تعطّل عامل).

    عامل مات وسط المعالجة يترك صفّه ``processing`` بلا مالك حيّ ⇒ لن يُلتقَط ثانيةً
    (المطالبة تخصّ ``pending`` فقط). هذا الاسترداد (best-effort، يُشغَّل دوريّاً)
    يُحرّر ما تجاوز عتبةً زمنيّةً. يُرجع عدد الصفوف المُستردَّة. يعتمد على
    ``idx_offline_pending_ops_processing`` (v138). RLS يُرشّح حسب المستأجِر تلقائيّاً.
    """
    row = await conn.fetchrow(
        """
        WITH reclaimed AS (
            UPDATE offline_pending_ops
            SET status = 'pending'
            WHERE status = 'processing'
              AND created_at < NOW() - ($1::int * INTERVAL '1 minute')
            RETURNING 1
        )
        SELECT COUNT(*) AS n FROM reclaimed
        """,
        older_than_minutes,
    )
    return int(row["n"]) if row else 0


async def clear_processed(conn: asyncpg.Connection, *, older_than_hours: int = 24) -> int:
    """ينظّف العمليّات المُنجزة الأقدم من العتبة (retention). يُرجع العدد المحذوف."""
    row = await conn.fetchrow(
        """
        WITH deleted AS (
            DELETE FROM offline_pending_ops
            WHERE status = 'processed'
              AND processed_at < NOW() - ($1::int * INTERVAL '1 hour')
            RETURNING 1
        )
        SELECT COUNT(*) AS n FROM deleted
        """,
        older_than_hours,
    )
    return int(row["n"]) if row else 0


# ─── غلاف عالي المستوى للمسارات (best-effort، fail-safe) ─────────────


async def persist_pending_best_effort(op: PendingOperation, user: object) -> bool:
    """يُدِيم عمليّة معلّقة best-effort: لا قاعدة ⇒ no-op (يبقى الذاكريّ مرجعاً).

    يُستدعى من المسارات بعد ``record_operation_offline`` (المسار الذاكريّ يبقى
    مصدر الحقيقة للدورة الجارية). الهدف: نجاة العمليّة من إعادة تشغيل العمليّة.

    fail-safe بالكامل: حين ``_DB_POOL is None`` (DATABASE_URL غير مضبوط — تطوير/CI)
    يعود ``False`` فوراً بلا قاعدة. وأيّ خطأ قاعدة يُبتلَع (لا يُفشِل الطلب — العمليّة
    حاضرة في الـqueue الذاكريّ). يُرجع ``True`` فقط إن كُتبت بدوام فعليّاً.

    الاستيراد كسول لتفادي الدوران: ``api.main`` يستورد المسارات في نهايته.
    """
    import logging

    try:
        from api.main import _DB_POOL, tenant_connection
    except Exception:  # noqa: BLE001 - بيئة بلا main (اختبار وحدة نقيّ)
        return False

    if _DB_POOL is None:
        return False

    try:
        async with tenant_connection(user) as conn:
            await enqueue_pending(conn, op=op, tenant_id=str(op.tenant_id))
        return True
    except Exception as exc:  # noqa: BLE001 - fail-safe: الذاكريّ يبقى مرجعاً
        logging.warning("offline_pending: durable enqueue failed for %s: %s", op.op_id, exc)
        return False
