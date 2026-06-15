"""
services/sahool-platform/api/command_store.py — Server-Side Idempotency

نظير mobile/src/sync/syncEngine.ts — هذه الطبقة على الـserver:
  - يستقبل command_id من الـmobile
  - لو الـcommand مرّ من قبل → يُرجع الـcached result (بدون إعادة تنفيذ)
  - يضمن "exactly-once logical execution" حتّى لو الـclient أعاد الطلب ١٠٠ مرّة

الأسباب الفنّيّة الحقيقيّة لهذه الطبقة:
  ١. شبكة ضعيفة → mobile يُعيد POST → الـserver كان نفّذ فعلاً → ازدواج
  ٢. إعادة تشغيل الـserver أثناء الـrequest → race condition
  ٣. مزامنة batch من mobile بعد ٤٨ ساعة offline → ترتيب + idempotency

ملاحظة منهجيّة:
  هذه ليست "Deterministic Command Execution Kernel" كما زعم المستند الخارجي.
  هي ببساطة: idempotency على مستوى الـDB + lifecycle validation. لا أكثر.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager as _asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


# ─── Types ──────────────────────────────────────────────────────


class CommandStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CommandSource(str, Enum):
    MOBILE = "mobile"
    WEB = "web"
    EDGE = "edge"
    SCHEDULER = "scheduler"


@dataclass
class Command:
    """تمثيل الـcommand — يطابق الـSQL schema في v10."""

    command_id: str
    command_type: str
    actor_id: str
    tenant_id: str
    payload: dict[str, Any]
    source: CommandSource
    status: CommandStatus = CommandStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    retry_count: int = 0
    created_at: datetime | None = None

    @classmethod
    def new(
        cls,
        command_type: str,
        actor_id: str,
        tenant_id: str,
        payload: dict[str, Any],
        source: CommandSource = CommandSource.MOBILE,
        command_id: str | None = None,
    ) -> Command:
        return cls(
            command_id=command_id or str(uuid.uuid4()),
            command_type=command_type,
            actor_id=actor_id,
            tenant_id=tenant_id,
            payload=payload,
            source=source,
        )


@dataclass
class DispatchResult:
    command_id: str
    status: CommandStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    was_duplicate: bool = False


# ─── Command Store (DB layer) ───────────────────────────────────


class CommandStore:
    """CRUD على جدول commands. لا منطق أعمال."""

    def __init__(self, pool: asyncpg.Pool, conn=None):
        self.pool = pool
        self._conn = conn

    @_asynccontextmanager
    async def _acquire(self):
        """conn من tenant_connection (RLS مُطبَّق) أو من الـpool (توافق خلفي).

        مسار الطلب يمرّر conn دائماً (main.py يُنشئ CommandStore بـconn من
        tenant_connection)، فيُطبَّق app.current_tenant. مسار الـpool احتياطيّ
        خلفيّ بلا سياق مستأجِر؛ تحت الدور المُقيَّد (NOBYPASSRLS/FORCE RLS) لا
        يُستخدَم على مسار طلب — يحتاج دوراً خدميّاً مخصّصاً إن استُعمل خلفيّاً.
        """
        if getattr(self, "_conn", None) is not None:
            yield self._conn
        else:
            async with self.pool.acquire() as c:
                yield c

    async def get(self, command_id: str) -> Command | None:
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM commands WHERE command_id = $1",
                uuid.UUID(command_id),
            )
            if not row:
                return None
            return self._row_to_command(row)

    async def insert(self, cmd: Command) -> bool:
        """يدخل الـcommand. Returns True لو أُدخِل، False لو موجود مسبقاً."""
        async with self._acquire() as conn:
            result = await conn.execute(
                """
                INSERT INTO commands
                    (command_id, command_type, actor_id, tenant_id, payload, source, status)
                VALUES ($1, $2, $3, $4, $5, $6, 'pending')
                ON CONFLICT (command_id) DO NOTHING
                """,
                uuid.UUID(cmd.command_id),
                cmd.command_type,
                cmd.actor_id,
                uuid.UUID(cmd.tenant_id),
                json.dumps(cmd.payload),
                cmd.source.value,
            )
            # asyncpg.execute returns "INSERT 0 N" — N=1 if inserted
            return result.endswith("1")

    async def mark_processing(self, command_id: str) -> None:
        async with self._acquire() as conn:
            await conn.execute(
                "UPDATE commands SET status = 'processing' WHERE command_id = $1",
                uuid.UUID(command_id),
            )

    async def mark_succeeded(self, command_id: str, result: dict[str, Any]) -> None:
        async with self._acquire() as conn:
            await conn.execute(
                """
                UPDATE commands
                SET status = 'succeeded', result = $2, error = NULL
                WHERE command_id = $1
                """,
                uuid.UUID(command_id),
                json.dumps(result),
            )

    async def mark_failed(self, command_id: str, error: str) -> None:
        async with self._acquire() as conn:
            await conn.execute(
                """
                UPDATE commands
                SET status = 'failed',
                    error = $2,
                    retry_count = retry_count + 1
                WHERE command_id = $1
                """,
                uuid.UUID(command_id),
                error[:500],
            )

    def _row_to_command(self, row) -> Command:
        payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
        result = None
        if row["result"]:
            result = row["result"] if isinstance(row["result"], dict) else json.loads(row["result"])
        return Command(
            command_id=str(row["command_id"]),
            command_type=row["command_type"],
            actor_id=row["actor_id"],
            tenant_id=str(row["tenant_id"]),
            payload=payload,
            source=CommandSource(row["source"]),
            status=CommandStatus(row["status"]),
            result=result,
            error=row["error"],
            retry_count=row["retry_count"],
            created_at=row["created_at"],
        )


# ─── Dispatcher ─────────────────────────────────────────────────

HandlerFn = Callable[[Command], "Awaitable[dict[str, Any]]"]


class CommandDispatcher:
    """
    Routes commands to handlers + enforces idempotency.

    Usage:
        dispatcher.register("field.create", create_field_handler)
        result = await dispatcher.dispatch(cmd)
    """

    def __init__(self, store: CommandStore):
        self.store = store
        self._handlers: dict[str, HandlerFn] = {}

    def register(self, command_type: str, handler: HandlerFn) -> None:
        if command_type in self._handlers:
            raise ValueError(f"handler for {command_type} already registered")
        self._handlers[command_type] = handler

    async def dispatch(self, cmd: Command) -> DispatchResult:
        # ١. Idempotency gate
        existing = await self.store.get(cmd.command_id)
        if existing:
            if existing.status == CommandStatus.SUCCEEDED:
                # Duplicate — أرجع الـcached result
                return DispatchResult(
                    command_id=cmd.command_id,
                    status=CommandStatus.SUCCEEDED,
                    result=existing.result,
                    was_duplicate=True,
                )
            if existing.status == CommandStatus.PROCESSING:
                # في الـmiddle of processing — أرجع pending
                return DispatchResult(
                    command_id=cmd.command_id,
                    status=CommandStatus.PROCESSING,
                    was_duplicate=True,
                )
            if existing.status == CommandStatus.FAILED:
                # Retry attempt — مسموح، نعيد التنفيذ
                logger.info(
                    f"Retrying failed command {cmd.command_id} (attempt {existing.retry_count + 1})"
                )
            # else PENDING → fall through to insert (race condition fix below)

        # ٢. Insert (idempotent — ON CONFLICT DO NOTHING)
        was_new = await self.store.insert(cmd)
        if not was_new:
            # Race condition: تمّ insert من thread آخر — أعد المحاولة
            return await self.dispatch(cmd)

        # ٣. Resolve handler
        handler = self._handlers.get(cmd.command_type)
        if not handler:
            err = f"no handler for command type: {cmd.command_type}"
            await self.store.mark_failed(cmd.command_id, err)
            return DispatchResult(
                command_id=cmd.command_id,
                status=CommandStatus.FAILED,
                error=err,
            )

        # ٤. Execute
        await self.store.mark_processing(cmd.command_id)
        try:
            result = await handler(cmd)
            await self.store.mark_succeeded(cmd.command_id, result)
            return DispatchResult(
                command_id=cmd.command_id,
                status=CommandStatus.SUCCEEDED,
                result=result,
            )
        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)[:200]}"
            await self.store.mark_failed(cmd.command_id, err_msg)
            logger.exception(f"command {cmd.command_id} failed")
            return DispatchResult(
                command_id=cmd.command_id,
                status=CommandStatus.FAILED,
                error=err_msg,
            )

    def registered_types(self) -> list[str]:
        return sorted(self._handlers.keys())
