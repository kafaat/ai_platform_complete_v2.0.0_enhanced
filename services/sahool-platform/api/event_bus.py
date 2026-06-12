"""
services/sahool-platform/api/event_bus.py — Reliable Event Emission

⚠ ملاحظة منهجيّة عن المستند الخارجي (Event Ingestion Gateway):
   المستند الخارجي اقترح:
       await write_to_postgis(event)
       await publish_event(event)   # NATS
       await enqueue_event(event)   # Redis

   هذا النمط له ٣ مشاكل حقيقيّة:
       ١. لو فشل NATS بعد write_to_postgis → divergence (DB له، NATS لا)
       ٢. لو فشل Redis بعد NATS → triple-write inconsistency
       ٣. asyncpg.connect() في كل call → connection leak

   الحلّ الصحيح (Outbox Pattern):
       INSERT events + INSERT outbox  (نفس الـtransaction → atomic)
                          ↓
                worker منفصل يقرأ outbox → NATS → mark sent

   النتيجة: at-least-once delivery مضمونة، لا divergence ممكن.

ما يفعله هذا الملف:
   ١. EventBus.emit() — يُدخِل event + outbox row في transaction واحد
   ٢. OutboxWorker — background task يقرأ outbox ويُرسل لـNATS
   ٣. helper functions للـcommon events (field.created, etc.)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager as _asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


# ─── Event types (catalog) ──────────────────────────────────────


class EventType(str, Enum):  # noqa: UP042 (intentional str-mixin for JSON/Pydantic value serialization)
    # Field lifecycle
    FIELD_CREATED = "field.created"
    FIELD_UPDATED = "field.updated"
    FIELD_GEOMETRY_CHANGED = "field.geometry_changed"
    FIELD_DELETED = "field.deleted"

    # Lifecycle transitions (state machine)
    LIFECYCLE_TRANSITIONED = "lifecycle.transitioned"

    # Season
    SEASON_CREATED = "season.created"

    # Activity (عمليّة حقليّة عامّة — تكمّل أحداث operation.* المحدّدة)
    ACTIVITY_RECORDED = "activity.recorded"

    # Operations
    PLANTING_STARTED = "operation.planting.started"
    PLANTING_COMPLETED = "operation.planting.completed"
    IRRIGATION_STARTED = "operation.irrigation.started"
    IRRIGATION_COMPLETED = "operation.irrigation.completed"
    FERTILIZER_APPLIED = "operation.fertilizer.applied"
    PESTICIDE_APPLIED = "operation.pesticide.applied"
    HARVEST_STARTED = "operation.harvest.started"
    HARVEST_COMPLETED = "operation.harvest.completed"

    # TrueUp (yield calibration)
    TRUEUP_APPLIED = "trueup.applied"

    # Sensors / Remote sensing
    NDVI_OBSERVATION = "remote_sensing.ndvi.observed"
    SOIL_SAMPLE_RECORDED = "soil.sample.recorded"
    WEATHER_RAIN = "weather.rain"
    MOISTURE_LOW = "weather.moisture.low"

    # AI suggestions (NOT decisions — human-in-loop)
    AI_SUGGESTION = "ai.suggestion.generated"
    AI_ANOMALY_DETECTED = "ai.anomaly.detected"


class EventSource(str, Enum):  # noqa: UP042 (intentional str-mixin for JSON/Pydantic value serialization)
    MOBILE = "mobile"
    WEB = "web"
    EDGE = "edge"
    SCHEDULER = "scheduler"
    SYSTEM = "system"
    AI = "ai"
    SENSOR = "sensor"


@dataclass
class EmittedEvent:
    event_id: str | None  # None إن كان duplicate
    was_duplicate: bool
    outbox_id: int | None = None


# ─── EventBus ───────────────────────────────────────────────────


class EventBus:
    """
    Atomically emits events:
        - INSERT into events
        - INSERT into event_outbox  (same transaction)
        - OutboxWorker handles NATS publish asynchronously

    Idempotency: نفس الـ(type, entity, payload_hash) في نفس اليوم = duplicate
                 → DB يرفضه عبر UNIQUE INDEX، الـmethod يُرجع was_duplicate=True
    """

    def __init__(self, pool: asyncpg.Pool, conn=None):
        import asyncpg as _ap  # noqa: F401

        self.pool = pool
        self._conn = conn

    @_asynccontextmanager
    async def _acquire(self):
        """conn من tenant_connection (RLS مُطبَّق) أو من الـpool (توافق خلفي)."""
        if getattr(self, "_conn", None) is not None:
            yield self._conn
        else:
            async with self.pool.acquire() as c:
                yield c

    async def emit(
        self,
        event_type: EventType,
        entity_type: str,
        entity_id: str,
        tenant_id: str,
        payload: dict[str, Any],
        source: EventSource = EventSource.SYSTEM,
        actor_id: str | None = None,
        command_id: str | None = None,
        occurred_at: datetime | None = None,
        correlation_id: str | None = None,
    ) -> EmittedEvent:
        """يُصدر event عبر emit_event SQL function (atomic).

        التوحيد: يُبنى الحدث عبر EventEnvelope (العقد الموحّد) ويُتحقَّق منه قبل أن
        يلمس القاعدة — فما يُصدَر موحّد الشكل ومُلتقِط خيط التتبّع (correlation/
        causation من core.correlation). صدق: المظروف غير الصالح يُرفَض بـValueError
        (لا إصدار صامت لحدثٍ مشوَّه).

        correlation_id: خيط التتبّع الموحّد (وسيط محجوز). idempotency: لا نحقنه
        داخل payload — emit_event يحسب payload_hash/dedup_key على p_payload::text،
        فحقنه يكسر الـdedup. تخزينه الدائم يحتاج عمود events.correlation_id مستقلّ
        (خطوة تالية، لا يمسّ الـhash) — لذا يبقى في المظروف للتحقّق/التتبّع فقط.
        """
        from core.event_schema import new_event, validate_envelope

        envelope = new_event(
            event_type.value,
            entity_type,
            entity_id,
            tenant_id,
            payload=payload,
            source=source.value,
            actor_id=actor_id,
            command_id=command_id,
            correlation_id=correlation_id,
        )
        errors = validate_envelope(envelope)
        if errors:
            raise ValueError(f"مظروف حدث غير صالح: {'; '.join(errors)}")
        args = envelope.to_emit_args()

        async with self._acquire() as conn:
            event_id = await conn.fetchval(
                """
                SELECT emit_event(
                    $1::text,           -- event_type
                    $2::text,           -- entity_type
                    $3::text,           -- entity_id (نصّيّ منذ v18 — معرّفات الحقول نصّيّة)
                    $4::uuid,           -- tenant_id
                    $5::jsonb,          -- payload
                    $6::text,           -- source
                    $7::text,           -- actor_id
                    $8::uuid,           -- command_id
                    $9::timestamptz     -- occurred_at
                )
                """,
                args["event_type"],
                args["entity_type"],
                str(args["entity_id"]),
                uuid.UUID(args["tenant_id"]),
                json.dumps(args["payload"]),
                args["source"],
                args["actor_id"],
                uuid.UUID(args["command_id"]) if args["command_id"] else None,
                occurred_at,
            )

            if event_id is None:
                # Duplicate — already emitted
                logger.debug(f"event duplicate (skipped): {event_type.value} on {entity_id}")
                return EmittedEvent(event_id=None, was_duplicate=True)

            return EmittedEvent(event_id=str(event_id), was_duplicate=False)

    async def query_entity_history(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """يرجع تاريخ entity (للـreplay engine)."""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT event_id, event_type, payload, source, actor_id,
                       command_id, occurred_at, recorded_at
                FROM events
                WHERE entity_type = $1 AND entity_id = $2
                ORDER BY occurred_at ASC
                LIMIT $3
                """,
                entity_type,
                entity_id,  # نصّيّ منذ v18 (لا تحويل UUID — كان يكسر معرّفات الحقول)
                limit,
            )
            return [
                {
                    "event_id": str(r["event_id"]),
                    "event_type": r["event_type"],
                    "payload": r["payload"]
                    if isinstance(r["payload"], dict)
                    else json.loads(r["payload"]),
                    "source": r["source"],
                    "actor_id": r["actor_id"],
                    "command_id": str(r["command_id"]) if r["command_id"] else None,
                    "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else None,
                    "recorded_at": r["recorded_at"].isoformat() if r["recorded_at"] else None,
                }
                for r in rows
            ]


# ─── OutboxWorker (background task) ─────────────────────────────


class OutboxWorker:
    """
    يقرأ event_outbox باستمرار ويُرسل إلى NATS.

    Usage:
        worker = OutboxWorker(pool, nats_client)
        asyncio.create_task(worker.run())   # background

    Retry policy: exponential backoff (max 5 retries → mark 'failed').
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        nats_publish_fn,  # async callable(subject, payload_bytes)
        batch_size: int = 50,
        poll_interval_sec: float = 1.0,
        max_retries: int = 5,
    ):
        self.pool = pool
        self.publish = nats_publish_fn
        self.batch_size = batch_size
        self.poll_interval = poll_interval_sec
        self.max_retries = max_retries
        self._running = False

    async def run(self):
        """Main loop — يتوقّف عند stop() أو cancel."""
        self._running = True
        logger.info("OutboxWorker started")
        while self._running:
            try:
                processed = await self._process_batch()
                if processed == 0:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"OutboxWorker error: {e}")
                await asyncio.sleep(self.poll_interval * 2)
        logger.info("OutboxWorker stopped")

    def stop(self):
        self._running = False

    async def _process_batch(self) -> int:
        """يأخذ batch من الـpending events ويرسلها.

        يفتح اتّصالاً من الـpool (OutboxWorker لا يملك conn مُنطّقاً — هو عامل
        خلفيّ عبر المستأجِرين، يقرأ outbox مباشرةً). يلفّ الكلّ في **معاملة صريحة**
        كي تبقى أقفال FOR UPDATE SKIP LOCKED محتجَزة حتى تحديث الحالة إلى 'sent'
        — يمنع الإرسال المزدوج عند تعدّد العمّال.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # SELECT FOR UPDATE SKIP LOCKED للـconcurrent workers safety
                rows = await conn.fetch(
                    """
                    SELECT o.outbox_id, o.event_id, o.nats_subject, o.retry_count,
                           e.event_type, e.entity_type, e.entity_id, e.tenant_id,
                           e.payload, e.occurred_at
                    FROM event_outbox o
                    JOIN events e ON e.event_id = o.event_id
                    WHERE o.status IN ('pending', 'failed')
                      AND o.retry_count < $1
                    ORDER BY o.created_at ASC
                    LIMIT $2
                    FOR UPDATE OF o SKIP LOCKED
                    """,
                    self.max_retries,
                    self.batch_size,
                )

                if not rows:
                    return 0

                for row in rows:
                    await self._send_one(conn, row)

                return len(rows)

    async def _send_one(self, conn, row):
        """يرسل event واحد إلى NATS مع retry tracking."""
        envelope = {
            "event_id": str(row["event_id"]),
            "event_type": row["event_type"],
            "entity_type": row["entity_type"],
            "entity_id": str(row["entity_id"]),
            "tenant_id": str(row["tenant_id"]),
            "payload": row["payload"]
            if isinstance(row["payload"], dict)
            else json.loads(row["payload"]),
            "occurred_at": row["occurred_at"].isoformat() if row["occurred_at"] else None,
        }

        try:
            await self.publish(row["nats_subject"], json.dumps(envelope).encode())
            await conn.execute(
                """
                UPDATE event_outbox
                SET status = 'sent', sent_at = NOW(), last_error = NULL
                WHERE outbox_id = $1
                """,
                row["outbox_id"],
            )
        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)[:200]}"
            new_retry = row["retry_count"] + 1
            new_status = "failed" if new_retry >= self.max_retries else "pending"
            await conn.execute(
                """
                UPDATE event_outbox
                SET retry_count = $1, last_attempt_at = NOW(),
                    last_error = $2, status = $3
                WHERE outbox_id = $4
                """,
                new_retry,
                err_msg,
                new_status,
                row["outbox_id"],
            )
            if new_status == "failed":
                # حدث ميّت (DLQ): استُنفدت المحاولات. تصعيد ERROR ليلتقطه الرصد/التنبيه
                # — يبقى في event_outbox (status='failed') لإعادة جدولته عبر
                # requeue_dead_letter بعد إصلاح السبب (راجع v_event_dead_letter).
                logger.error(
                    "DEAD_LETTER outbox_id=%s event=%s بعد %s محاولة: %s",
                    row["outbox_id"],
                    row["event_type"],
                    self.max_retries,
                    err_msg,
                )
            else:
                logger.warning(f"outbox send failed ({new_retry}/{self.max_retries}): {err_msg}")
