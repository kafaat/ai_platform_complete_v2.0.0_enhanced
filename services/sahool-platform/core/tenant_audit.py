"""core/tenant_audit.py — سجلّ تدقيق رفض العبور بين المستأجِرين والصلاحيّات.

سجلّ أمنيّ نقيّ في-الذاكرة (deque محدود) يرصد حالات الرفض: محاولة وصول لمورد خارج
نطاق المستأجِر (RLS ⇒ 404)، أو صلاحية غير كافية (403)، أو فشل مصادقة (401). يجعل
محاولات التسرّب العابر للمستأجِرين والرفض مرئيّةً للمراقبة بدل ضياعها في السجلّات.

نمط مطابق لـcore.automation_ledger (singleton + deque + recent/summary). صدق وخصوصيّة:
يُخزَّن فقط ما يُمرَّر — مُعرّفات (user_id/tenant_id الموجودة في الـJWT) لا أسرار/توكنات.
لا يرفع استثناءً (التدقيق لا يكسر المسار).

**الإدامة (قرار المالك 2026-11-14):** الحلقة في-الذاكرة تضيع عند إعادة التشغيل وهي لكلّ
عمليّة. ``DenialStore`` يُديم كلّ رفض في جدول ``audit_log`` القائم (مالكه وكاتبه
sahool-platform في db_ownership.yml؛ إلحاقيّ بمُنبِّه v9_append_only؛ RLS مفروض) بلا هجرة:
``action='denial:<kind>'``، والحقول في ``details`` نصّ JSON. الكتابة:

* **غير حاجبة:** ``record`` يُلحِق بطابور محدود في-الذاكرة فقط (آمن من خيط الـthreadpool
  الذي تعمل فيه تبعيّة ``require_permission`` المتزامنة). فشلُ القاعدة لا يقلب 403 إلى 500.
* **محدودة:** عاملٌ خلفيّ يُفرغ الطابور دفعاتٍ (``batch_size``) كلّ ``interval`` ثانية،
  معاملةٌ واحدة لكلّ دفعة لا لكلّ طلب؛ والطابور ``maxlen`` يُسقِط الأقدم ويَعُدّه.
* **منطّقة بالمستأجِر:** لكلّ مستأجِر في الدفعة ``set_config('app.current_tenant', …, true)``
  داخل المعاملة (WITH CHECK في السياسة يفرضه)، والحدث بلا مستأجِر (أو بمستأجِر ليس UUID)
  يُكتَب ``tenant_id = NULL`` فلا يقرؤه أيّ مستأجِر.

القراءة (``read``) على اتّصال ``tenant_connection`` المُنادي: مستأجِره فقط صراحةً
(``tenant_id = $1``) فوق RLS، والحدّ بعد المرشِّح. الحلقة تبقى احتياطاً حين تغيب القاعدة.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_KINDS = ("tenant_scope", "permission", "auth")


@dataclass
class DenialRecord:
    """سجلّ رفض واحد — مُعرّفات فقط (لا توكنات/أسرار)."""

    at: str  # ISO timestamp (UTC)
    kind: str  # tenant_scope | permission | auth
    user_id: str | None = None
    tenant_id: str | None = None
    resource: str | None = None
    action: str | None = None
    reason_ar: str | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class TenantAuditLog:
    """سجلّ تدقيق محدود (ring buffer) لحالات الرفض الأمنيّ — في-الذاكرة، آمن للحلقة."""

    def __init__(self, maxlen: int = 200, *, store: DenialStore | None = None) -> None:
        self._buf: deque[DenialRecord] = deque(maxlen=maxlen)
        self.maxlen = maxlen
        self.store = store

    def record(
        self,
        kind: str,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        resource: str | None = None,
        action: str | None = None,
        reason_ar: str | None = None,
        detail: dict | None = None,
    ) -> DenialRecord:
        """يسجّل حالة رفض — لا يرفع استثناءً أبداً (التدقيق لا يكسر المسار)."""
        rec = DenialRecord(
            at=datetime.now(UTC).isoformat(),
            kind=kind if kind in _KINDS else "permission",
            user_id=user_id,
            tenant_id=tenant_id,
            resource=resource,
            action=action,
            reason_ar=reason_ar,
            detail=detail or {},
        )
        self._buf.append(rec)
        if self.store is not None:
            try:
                self.store.enqueue(rec)
            except Exception as exc:  # noqa: BLE001 — الإدامة لا تكسر مسار الرفض
                logger.warning("denial persistence enqueue failed: %s", type(exc).__name__)
        return rec

    def _in_scope(self, tenant_id: str | None) -> list[DenialRecord]:
        """None is only for trusted in-process diagnostics, never a public HTTP default."""
        if tenant_id is None:
            return list(self._buf)
        return [r for r in self._buf if r.tenant_id == tenant_id]

    def recent(self, limit: int | None = None, *, tenant_id: str | None = None) -> list[dict]:
        """أحدث حالات الرفض ضمن نطاق المستأجر المحدد."""
        items = list(reversed(self._in_scope(tenant_id)))
        if limit is not None:
            items = items[: max(0, int(limit))]
        return [r.to_dict() for r in items]

    def summary(self, *, tenant_id: str | None = None) -> dict:
        """ملخّص معزول بالمستأجر (None للتشخيص الداخلي الموثوق فقط)."""
        rows = self._in_scope(tenant_id)
        by_kind: dict[str, int] = {}
        for r in rows:
            by_kind[r.kind] = by_kind.get(r.kind, 0) + 1
        last_at = rows[-1].at if rows else None
        return {
            "total": len(rows),
            "buffer_capacity": self.maxlen,
            "by_kind": by_kind,
            "last_at": last_at,
        }

    def clear(self) -> None:
        """يُفرّغ السجلّ (للاختبار/إعادة الضبط)."""
        self._buf.clear()


_ACTION_PREFIX = "denial:"
_DEFAULT_READ_LIMIT = 200

_INSERT_SQL = (
    "INSERT INTO audit_log (action, user_id, details, tenant_id, created_at) "
    "VALUES ($1, (SELECT u.id FROM users u WHERE u.id = $2::int), $3, $4::uuid, $5)"
)
_SELECT_SQL = (
    "SELECT details, created_at FROM audit_log "
    "WHERE tenant_id = $1::uuid AND action LIKE 'denial:%' "
    "ORDER BY created_at DESC, id DESC LIMIT $2"
)
_SUMMARY_SQL = (
    "SELECT action, count(*) AS n, max(created_at) AS last_at FROM audit_log "
    "WHERE tenant_id = $1::uuid AND action LIKE 'denial:%' GROUP BY action"
)


def _as_tenant_uuid(value: str | None) -> str | None:
    """مستأجِر قابل للتخزين في ``audit_log.tenant_id`` (UUID) أو None (بلا نسبة)."""
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _db_user_id(value: str | None) -> int | None:
    """``audit_log.user_id`` عدد صحيح بمفتاح أجنبيّ؛ المُعرّف غير العدديّ يبقى في details."""
    text = str(value or "")
    return int(text) if text.isdigit() and len(text) <= 9 else None


def denial_row(rec: DenialRecord) -> tuple[str | None, tuple[Any, ...]]:
    """(مستأجِر الكتابة، وسائط INSERT) لسجلّ رفض — نقيّة، تُختبَر بلا قاعدة."""
    tenant = _as_tenant_uuid(rec.tenant_id)
    details = json.dumps(rec.to_dict(), ensure_ascii=False, default=str, sort_keys=True)
    return tenant, (
        f"{_ACTION_PREFIX}{rec.kind}",
        _db_user_id(rec.user_id),
        details,
        tenant,
        datetime.fromisoformat(rec.at),
    )


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


class DenialStore:
    """إدامة سجلّات الرفض في ``audit_log`` — طابور محدود + عامل دفعات، best-effort.

    لا يعمل إلّا بعد ``bind(pool_getter)`` (يضبطه إقلاع المنصّة حين يوجد مسبح القاعدة)؛
    غير مربوط ⇒ ``enqueue`` لا يفعل شيئاً، فالسلوك في-الذاكرة كما كان.
    """

    def __init__(
        self,
        *,
        maxlen: int = 5000,
        batch_size: int = 200,
        interval: float = 1.0,
        write_timeout: float = 5.0,
    ) -> None:
        self._pending: deque[DenialRecord] = deque(maxlen=maxlen)
        self.maxlen = maxlen
        self.batch_size = batch_size
        self.interval = interval
        self.write_timeout = write_timeout
        self._pool_getter: Callable[[], Any] | None = None
        self._task: asyncio.Task | None = None
        self._lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None
        self.written = 0
        self.failed = 0
        self.dropped = 0

    # ── الربط ودورة الحياة ──
    @property
    def bound(self) -> bool:
        return self._pool_getter is not None

    def bind(self, pool_getter: Callable[[], Any]) -> None:
        self._pool_getter = pool_getter

    def unbind(self) -> None:
        self._pool_getter = None
        self._pending.clear()

    def stats(self) -> dict:
        return {
            "bound": self.bound,
            "pending": len(self._pending),
            "written": self.written,
            "failed": self.failed,
            "dropped": self.dropped,
        }

    def start(self) -> None:
        """يبدأ عامل الإفراغ الدوريّ على الحلقة الجارية (مرّة واحدة)."""
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        """يوقف العامل ثمّ يُفرغ ما تبقّى مرّةً أخيرة (قبل إغلاق المسبح) ويفكّ الربط."""
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self.flush()
        self.unbind()

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            await self.flush()

    # ── الكتابة ──
    def enqueue(self, rec: DenialRecord) -> None:
        """يُلحِق سجلّاً بالطابور — O(1)، بلا I/O، آمن من أيّ خيط؛ لا يرفع."""
        if self._pool_getter is None:
            return
        if len(self._pending) >= self.maxlen:
            self.dropped += 1  # deque(maxlen) يُسقِط الأقدم؛ نَعُدّه بدل أن يختفي صامتاً
        self._pending.append(rec)

    def _current_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock, self._lock_loop = asyncio.Lock(), loop
        return self._lock

    def _pool(self) -> Any:
        getter = self._pool_getter
        if getter is None:
            return None
        try:
            return getter()
        except Exception:  # noqa: BLE001 — مسبح غير متاح ⇒ لا إفراغ الآن
            return None

    async def flush(self) -> int:
        """يكتب كلّ المُعلَّق دفعاتٍ؛ يُعيد عدد الصفوف المكتوبة. لا يرفع أبداً.

        دفعةٌ فاشلة تُعَدّ في ``failed`` وتُسقَط (best-effort؛ تبقى في الحلقة في-الذاكرة)،
        ويتوقّف الإفراغ حتّى الدورة التالية فلا تُطرَق قاعدةٌ معطّلة في حلقة.
        """
        pool = self._pool()
        if pool is None or not self._pending:
            return 0
        written = 0
        async with self._current_lock():
            while self._pending:
                batch: list[DenialRecord] = []
                while self._pending and len(batch) < self.batch_size:
                    batch.append(self._pending.popleft())
                try:
                    await asyncio.wait_for(self._write(pool, batch), timeout=self.write_timeout)
                except Exception as exc:  # noqa: BLE001 — فشل التدقيق لا يكسر شيئاً
                    self.failed += len(batch)
                    logger.warning(
                        "denial persistence: %d record(s) not written: %s",
                        len(batch),
                        type(exc).__name__,
                    )
                    break
                written += len(batch)
        self.written += written
        return written

    async def _write(self, pool: Any, batch: list[DenialRecord]) -> None:
        groups: dict[str | None, list[tuple[Any, ...]]] = {}
        for rec in batch:
            tenant, args = denial_row(rec)
            groups.setdefault(tenant, []).append(args)
        async with pool.acquire() as conn:
            async with conn.transaction():  # معاملةٌ واحدة للدفعة كلّها
                for tenant, rows in groups.items():
                    # سياق المستأجِر بنطاق المعاملة (WITH CHECK)؛ "" ⇒ صفّ بلا مستأجِر.
                    await conn.execute(
                        "SELECT set_config('app.current_tenant', $1, true), "
                        "       set_config('app.current_user_id', '', true), "
                        "       set_config('app.current_role', '', true)",
                        tenant or "",
                    )
                    await conn.executemany(_INSERT_SQL, rows)

    # ── القراءة ──
    async def read_durable(
        self,
        connect: Callable[[], Any],
        tenant_id: str,
        limit: int | None,
        *,
        capacity: int,
    ) -> tuple[list[dict], dict] | None:
        """قراءة نقطة الإدارة من القاعدة، أو None ليعود المُنادي إلى الحلقة في-الذاكرة.

        يُفرغ المُعلَّق أوّلاً (قراءةُ ما كُتب للتوّ، لا بعد دورة العامل)، ثمّ يقرأ على
        ``connect()`` — ``tenant_connection(user)`` — بمهلة. غير مربوط/قاعدة معطّلة/مستأجِر
        ليس UUID ⇒ None (لا 500).
        """
        if not self.bound:
            return None
        await self.flush()

        async def _read() -> tuple[list[dict], dict]:
            async with connect() as conn:
                return await self.read(conn, tenant_id, limit, capacity=capacity)

        try:
            return await asyncio.wait_for(_read(), timeout=self.write_timeout)
        except Exception as exc:  # noqa: BLE001 — القراءة الدائمة تتدهور إلى الحلقة
            logger.warning("denial log durable read failed: %s", type(exc).__name__)
            return None

    async def read(
        self, conn: Any, tenant_id: str, limit: int | None, *, capacity: int
    ) -> tuple[list[dict], dict]:
        """(denials، summary) لمستأجِر المُنادي من القاعدة — الشكل نفسه للحلقة.

        ``conn`` اتّصالٌ من ``tenant_connection`` (سياق المُنادي). المرشِّح صريحٌ فوق RLS:
        ``tenant_id = $1`` يُقصي صفوف المستأجرين الآخرين وكلّ صفّ بلا مستأجِر (NULL).
        يرفع عند تعذّر القراءة (المُنادي يعود إلى الحلقة).
        """
        tenant = _as_tenant_uuid(tenant_id)
        if tenant is None:
            raise ValueError("tenant is not a UUID; the durable log cannot scope it")
        cap = _DEFAULT_READ_LIMIT if limit is None else max(0, int(limit))
        rows = await conn.fetch(_SELECT_SQL, tenant, cap)
        denials = []
        for row in rows:
            item = json.loads(row["details"])
            item["at"] = item.get("at") or _iso(row["created_at"])
            denials.append(item)
        by_kind: dict[str, int] = {}
        total, last = 0, None
        for row in await conn.fetch(_SUMMARY_SQL, tenant):
            kind = str(row["action"])[len(_ACTION_PREFIX) :]
            by_kind[kind] = by_kind.get(kind, 0) + int(row["n"])
            total += int(row["n"])
            if row["last_at"] is not None and (last is None or row["last_at"] > last):
                last = row["last_at"]
        summary = {
            "total": total,
            "buffer_capacity": capacity,
            "by_kind": by_kind,
            "last_at": _iso(last),
        }
        return denials, summary


# singletons مشتركة بين مواضع الرفض ونقطة القراءة وإقلاع المنصّة.
DENIAL_STORE = DenialStore()
AUDIT = TenantAuditLog(store=DENIAL_STORE)
