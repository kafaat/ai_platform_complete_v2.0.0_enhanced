"""
services/sahool-platform/api/field_lifecycle.py — Field Lifecycle Engine

State machine للحقل (موسم واحد):

    CREATED → PREPARED → PLANTED → GROWING → MATURE → HARVESTED → POST_HARVEST
                                                                       ↓
                                                                  (يعود إلى PREPARED للموسم التالي)

الـSQL trigger في migrations/v10 يفرض الانتقالات. هذه الـPython API هي
الواجهة المُسجَّلة في الـCommandDispatcher.

ملاحظة منهجيّة (صادقة):
  المستند الخارجي زعم أنّ هذا يُحوّل النظام إلى "Temporal Agricultural Operating
  Kernel". هذا تأطير مُضخَّم. الواقع: state machine بسيط يمنع انتقالات غير
  منطقيّة (مثل "حصاد حقل لم يُزرع"). هذا مفيد لكنّه ليس "operating kernel".
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


# ─── Stages ─────────────────────────────────────────────────────


class LifecycleStage(str, Enum):  # noqa: UP042 (intentional str-mixin for JSON/Pydantic value serialization)
    CREATED = "CREATED"
    PREPARED = "PREPARED"
    PLANTED = "PLANTED"
    GROWING = "GROWING"
    MATURE = "MATURE"
    HARVESTED = "HARVESTED"
    POST_HARVEST = "POST_HARVEST"


VALID_TRANSITIONS: dict[LifecycleStage, list[LifecycleStage]] = {
    LifecycleStage.CREATED: [LifecycleStage.PREPARED],
    LifecycleStage.PREPARED: [LifecycleStage.PLANTED],
    LifecycleStage.PLANTED: [LifecycleStage.GROWING],
    LifecycleStage.GROWING: [LifecycleStage.MATURE],
    LifecycleStage.MATURE: [LifecycleStage.HARVESTED],
    LifecycleStage.HARVESTED: [LifecycleStage.POST_HARVEST],
    LifecycleStage.POST_HARVEST: [LifecycleStage.PREPARED],  # موسم جديد
}


def is_valid_transition(from_stage: LifecycleStage, to_stage: LifecycleStage) -> bool:
    """نظير SQL function `valid_lifecycle_transition` للتحقّق المسبق."""
    return to_stage in VALID_TRANSITIONS.get(from_stage, [])


# ─── Types ──────────────────────────────────────────────────────


@dataclass
class FieldLifecycle:
    lifecycle_id: str
    field_id: str
    tenant_id: str
    season_id: str | None
    current_stage: LifecycleStage
    stage_entered_at: datetime


@dataclass
class LifecycleTransition:
    transition_id: str
    lifecycle_id: str
    from_stage: LifecycleStage | None
    to_stage: LifecycleStage
    transitioned_at: datetime
    changed_by: str
    command_id: str | None
    reason: str | None


# ─── Engine ─────────────────────────────────────────────────────


class LifecycleError(Exception):
    """خطأ في الـlifecycle (انتقال غير صالح، lifecycle مفقود، إلخ)."""


class FieldLifecycleEngine:
    """
    Operations:
        - get_or_create(field_id, season_id) → FieldLifecycle
        - transition(lifecycle_id, to_stage, changed_by, command_id=None, reason=None) → LifecycleTransition
        - get_history(lifecycle_id) → List[LifecycleTransition]
        - get_state(field_id, season_id) → FieldLifecycle | None
    """

    def __init__(self, pool: asyncpg.Pool):
        # Lazy import — pure logic functions تعمل بدون asyncpg
        import asyncpg as _ap  # noqa: F401

        self.pool = pool

    async def get_or_create(
        self,
        field_id: str,
        tenant_id: str,
        season_id: str | None = None,
    ) -> FieldLifecycle:
        async with self.pool.acquire() as conn:
            # حاول الجلب أوّلاً
            row = await conn.fetchrow(
                """
                SELECT * FROM field_lifecycle
                WHERE field_id = $1 AND (season_id = $2 OR (season_id IS NULL AND $2 IS NULL))
                """,
                field_id,  # نصّيّ منذ v18 (fields.field_id VARCHAR)
                uuid.UUID(season_id) if season_id else None,
            )
            if row:
                return self._row_to_lifecycle(row)

            # أنشئ جديد
            lifecycle_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO field_lifecycle
                    (lifecycle_id, field_id, tenant_id, season_id, current_stage)
                VALUES ($1, $2, $3, $4, 'CREATED')
                """,
                uuid.UUID(lifecycle_id),
                field_id,  # نصّيّ منذ v18 (fields.field_id VARCHAR)
                uuid.UUID(tenant_id),
                uuid.UUID(season_id) if season_id else None,
            )
            return FieldLifecycle(
                lifecycle_id=lifecycle_id,
                field_id=field_id,
                tenant_id=tenant_id,
                season_id=season_id,
                current_stage=LifecycleStage.CREATED,
                stage_entered_at=datetime.now(UTC),
            )

    async def transition(
        self,
        lifecycle_id: str,
        to_stage: LifecycleStage,
        changed_by: str,
        command_id: str | None = None,
        reason: str | None = None,
        occurred_at: datetime | None = None,
        enforcement_mode: str = "LIVE",
    ) -> LifecycleTransition:
        """
        ينقل الـlifecycle إلى to_stage.

        الـSQL trigger سيرفض الانتقال إن كان غير صالح (يرفع exception).
        نلتقطها ونحوّلها إلى LifecycleError بـmessage واضح.

        Temporal Invariant (مراجعة 10): إن مُرّر occurred_at وكان أقدم من
        آخر انتقال مسجّل، يُرفَض الانتقال (منع stale/out-of-order يفسد الحالة).
        """
        async with self.pool.acquire() as conn:
            # تحقّق pre-flight (يعطي رسالة خطأ أوضح من DB)
            current = await conn.fetchval(
                "SELECT current_stage FROM field_lifecycle WHERE lifecycle_id = $1",
                uuid.UUID(lifecycle_id),
            )
            if current is None:
                raise LifecycleError(f"lifecycle {lifecycle_id} not found")

            current_stage = LifecycleStage(current)
            if not is_valid_transition(current_stage, to_stage):
                allowed = VALID_TRANSITIONS.get(current_stage, [])
                raise LifecycleError(
                    f"Invalid transition: {current_stage.value} → {to_stage.value}. "
                    f"Allowed from {current_stage.value}: {[s.value for s in allowed]}"
                )

            # Temporal Invariant (مراجعة 10): امنع الانتقال المتأخّر/خارج الترتيب.
            # المقارنة ضدّ آخر occurred_at (وقت الحقيقة) لا transitioned_at (NOW).
            # mode=LIVE يرفض الـregression؛ mode=REPLAY يسمح (إعادة بناء تاريخيّة).
            # الرفض لا يُفقَد — يُسجَّل في lifecycle_temporal_rejections للتسوية.
            if occurred_at is not None and enforcement_mode == "LIVE":
                last = await conn.fetchrow(
                    """SELECT occurred_at, seq FROM field_lifecycle_transitions
                       WHERE lifecycle_id = $1 AND occurred_at IS NOT NULL
                       ORDER BY occurred_at DESC, seq DESC LIMIT 1""",
                    uuid.UUID(lifecycle_id),
                )
                if last and last["occurred_at"] is not None and occurred_at < last["occurred_at"]:
                    # سجّل الرفض للتسوية (لا نرمي الحقيقة المتأخّرة)
                    await conn.execute(
                        """INSERT INTO lifecycle_temporal_rejections
                             (tenant_id, lifecycle_id, to_stage, occurred_at,
                              last_occurred_at, reason)
                           VALUES (NULLIF(current_setting('app.current_tenant',true),'')::uuid,
                                   $1, $2, $3, $4, $5)""",
                        uuid.UUID(lifecycle_id),
                        to_stage.value,
                        occurred_at,
                        last["occurred_at"],
                        "temporal regression: occurred_at أقدم من آخر انتقال",
                    )
                    raise LifecycleError(
                        f"Temporal regression مرفوض (LIVE): occurred_at "
                        f"({occurred_at.isoformat()}) أقدم من آخر occurred_at "
                        f"({last['occurred_at'].isoformat()}). سُجِّل للتسوية، لم يُفقَد."
                    )

            # نفّذ الـtransition (الـtrigger سيُحدّث current_stage تلقائياً)
            transition_id = str(uuid.uuid4())
            try:
                await conn.execute(
                    """
                    INSERT INTO field_lifecycle_transitions
                        (transition_id, lifecycle_id, to_stage, changed_by, command_id, reason, occurred_at)
                    VALUES ($1, $2, $3, $4, $5, $6, COALESCE($7::timestamptz, NOW()))
                    """,
                    uuid.UUID(transition_id),
                    uuid.UUID(lifecycle_id),
                    to_stage.value,
                    changed_by,
                    uuid.UUID(command_id) if command_id else None,
                    reason,
                    occurred_at,
                )
            except asyncpg.PostgresError as e:
                # الـtrigger رفض (نادر لأنّنا تحقّقنا فوق، لكن دفاعياً)
                raise LifecycleError(f"DB rejected transition: {e}") from e

            return LifecycleTransition(
                transition_id=transition_id,
                lifecycle_id=lifecycle_id,
                from_stage=current_stage,
                to_stage=to_stage,
                transitioned_at=datetime.now(UTC),
                changed_by=changed_by,
                command_id=command_id,
                reason=reason,
            )

    async def get_history(self, lifecycle_id: str) -> list[LifecycleTransition]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM field_lifecycle_transitions
                WHERE lifecycle_id = $1
                ORDER BY transitioned_at ASC
                """,
                uuid.UUID(lifecycle_id),
            )
            return [
                LifecycleTransition(
                    transition_id=str(r["transition_id"]),
                    lifecycle_id=str(r["lifecycle_id"]),
                    from_stage=LifecycleStage(r["from_stage"]) if r["from_stage"] else None,
                    to_stage=LifecycleStage(r["to_stage"]),
                    transitioned_at=r["transitioned_at"],
                    changed_by=r["changed_by"],
                    command_id=str(r["command_id"]) if r["command_id"] else None,
                    reason=r["reason"],
                )
                for r in rows
            ]

    async def get_state(
        self,
        field_id: str,
        season_id: str | None = None,
    ) -> FieldLifecycle | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM field_lifecycle
                WHERE field_id = $1 AND (season_id = $2 OR (season_id IS NULL AND $2 IS NULL))
                """,
                field_id,  # نصّيّ منذ v18 (fields.field_id VARCHAR)
                uuid.UUID(season_id) if season_id else None,
            )
            return self._row_to_lifecycle(row) if row else None

    def _row_to_lifecycle(self, row) -> FieldLifecycle:
        return FieldLifecycle(
            lifecycle_id=str(row["lifecycle_id"]),
            field_id=str(row["field_id"]),
            tenant_id=str(row["tenant_id"]),
            season_id=str(row["season_id"]) if row["season_id"] else None,
            current_stage=LifecycleStage(row["current_stage"]),
            stage_entered_at=row["stage_entered_at"],
        )
