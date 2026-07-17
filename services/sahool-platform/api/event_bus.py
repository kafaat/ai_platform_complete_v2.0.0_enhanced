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
import os
import uuid
from contextlib import asynccontextmanager as _asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from .feature_registry import is_enabled

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


# ─── H2: علم نشر NATS (feature flag، default OFF) ──────────────────
# إطار «implemented-but-off-by-default»: الأحداث تُسجَّل دائماً في events+event_outbox
# (record_decision_only، ذرّيّ لا يُفقَد)؛ هذا العلم يحرس **تشغيل ناشر NATS فقط**
# (OutboxWorker → NATS). OFF (افتراضيّ) ⇒ لا يُشغَّل الناشر، الأحداث تبقى في outbox
# بصدق (publishers يتيمون آمنون). ON ⇒ يُشغَّل الناشر فيُسلّم (publish_event). ليس علم
# راوتر ⇒ خارج feature_registry.FEATURE_FLAGS. **ON env-unverified** (يحتاج NATS حيّاً).
NATS_PUBLISHERS_FLAG = "FEATURE_NATS_PUBLISHERS"


def nats_publishers_enabled() -> bool:
    """هل ناشرو NATS مُفعَّلون؟ default OFF — الأحداث تبقى في outbox (record_decision_only)."""
    return is_enabled(NATS_PUBLISHERS_FLAG, os.getenv(NATS_PUBLISHERS_FLAG))


# ─── Outbox retry backoff (pure) ────────────────────────────────

# أساس وسقف التراجع الأسّيّ (exponential backoff) للـoutbox. القيم module-level
# كي تتطابق دالّة بايثون النقيّة `outbox_backoff_seconds` مع بوّابة الزمن في SQL
# (انظر OutboxWorker._process_batch). تغييرهما هنا يغيّر السلوكين معاً.
OUTBOX_BACKOFF_BASE_SECONDS: float = 2.0
OUTBOX_BACKOFF_MAX_SECONDS: float = 3600.0  # سقف ساعة واحدة


def outbox_backoff_seconds(
    retry_count: int,
    base: float = OUTBOX_BACKOFF_BASE_SECONDS,
    cap: float = OUTBOX_BACKOFF_MAX_SECONDS,
) -> float:
    """تأخير التراجع الأسّيّ (بالثواني) قبل إعادة محاولة صفّ outbox فاشل.

    الصيغة: ``min(cap, base * 2**retry_count)`` — نقيّة، حتميّة، بلا آثار جانبيّة.

    ``retry_count`` هنا هو عدد المحاولات الفاشلة السابقة (العمود
    ``event_outbox.retry_count``). صفٌّ لم يُحاوَل بعد (retry_count=0) يحصل على
    أصغر تأخير = ``base`` ثانية، لكن البوّابة الزمنيّة في SELECT تتجاوزه عملياً
    عندما يكون ``last_attempt_at IS NULL`` (محاولة فوريّة، سلوك غير متغيّر).

    الجدول الافتراضيّ (base=2s, cap=3600s):
        retry_count=0 →    2s
        retry_count=1 →    4s
        retry_count=2 →    8s
        retry_count=3 →   16s
        retry_count=4 →   32s
        retry_count=5 →   64s
        ...
        retry_count=11 → 4096s → يُقصّ إلى 3600s (السقف)
    وكلّ ما بعده مُثبَّت عند 3600s (ساعة).
    """
    if retry_count < 0:
        retry_count = 0
    return min(cap, base * (2.0**retry_count))


def dead_letter_summary(rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    """يُشكّل ملخّص DLQ من صفوف خام (pure) — لا قاعدة بيانات، قابل للاختبار offline.

    ``rows`` صفوف الأحداث الميّتة (status='failed' AND retry_count>=max). يُرجع
    عدّاً + عيّنة (أوّل 50) مُشكَّلة بمفاتيح ثابتة، فيبقى تشكيل الخرج منفصلاً عن
    تنفيذ الـSQL ويمكن اختباره بلا خدمات.
    """
    rows = rows or []

    def _shape(r: dict[str, Any]) -> dict[str, Any]:
        last = r.get("last_attempt_at")
        return {
            "outbox_id": r.get("outbox_id"),
            "event_id": str(r["event_id"]) if r.get("event_id") is not None else None,
            "nats_subject": r.get("nats_subject"),
            "retry_count": r.get("retry_count"),
            "last_error": r.get("last_error"),
            "last_attempt_at": last.isoformat() if hasattr(last, "isoformat") else last,
        }

    return {
        "total": len(rows),
        "sample": [_shape(r) for r in rows[:50]],
    }


# ─── Event types (catalog) ──────────────────────────────────────


class EventType(str, Enum):  # noqa: UP042 (intentional str-mixin for JSON/Pydantic value serialization)
    # Field lifecycle
    FIELD_CREATED = "field.created"
    FIELD_UPDATED = "field.updated"
    FIELD_GEOMETRY_CHANGED = "field.geometry_changed"
    # استرجاع حدود الحقل لمراجعة سابقة (revert) — يُصدَر عند POST استرجاع الحدود في
    # fields.py؛ حدث مستقلّ عن التغيير العاديّ ليُتتبَّع/يُدقَّق في مجرى الأحداث.
    FIELD_GEOMETRY_REVERTED = "field.geometry_reverted"
    # طلب تحديث صور الأقمار للحقل (زرّ «تحديث صور الأقمار» / مسار manual.refresh) — يُصدَر
    # عند نقطة POST /imagery/refresh بعد استدعاء raster (imagery/best + process-from-stac)،
    # مرساةً لفعل حقيقيّ (طلب معالجة مُستهدَفة) يجعله متتبَّعاً/مدقَّقاً في مجرى الأحداث.
    FIELD_IMAGERY_REFRESH_REQUESTED = "field.imagery.refresh_requested"
    # عند نقطة POST /imagery/backfill (بوّابة المنصّة تحقن X-Agent-Token وتمرّر إلى
    # raster) — طلب سلسلة تاريخيّة (24m/3y/5y) يُتتبَّع/يُدقَّق في مجرى الأحداث.
    FIELD_IMAGERY_BACKFILL_REQUESTED = "field.imagery.backfill_requested"
    # دمج آليّ لتعديل offline متعارض غير متقاطع (Auto-merge L3) — تدقيق صريح.
    OFFLINE_MERGE_AUTO = "offline.merge.auto"
    FIELD_DELETED = "field.deleted"
    # تبدّل الحالة القانونيّة الموحّدة (Canonical Field State) — صلاحيّة القرار/نمط
    # التنفيذ تغيّرا بعد تغيّر مدخلات (موسم/تربة/طقس). يستهلكه وكيل الإشعارات (تغذية حيّة).
    FIELD_STATE_CHANGED = "field.state_changed"

    # Lifecycle transitions (state machine)
    LIFECYCLE_TRANSITIONED = "lifecycle.transitioned"

    # Season
    SEASON_CREATED = "season.created"
    SEASON_CLOSED = "season.closed"
    SEASON_UPDATED = "season.updated"

    # Activity (عمليّة حقليّة عامّة — تكمّل أحداث operation.* المحدّدة)
    ACTIVITY_RECORDED = "activity.recorded"

    # Alerts (تنبيهات زراعيّة) — تجعل التنبيهات تفاعليّة عبر الأحداث بدل المسح الدوريّ.
    # يستهلكها وكيل الإشعارات (sahool.events.>) لبثّ فوريّ عبر WebSocket/القنوات.
    ALERT_CREATED = "alert.created"
    ALERT_ACKNOWLEDGED = "alert.acknowledged"

    # إيصال تسليم الإشعار (إغلاق دورة الإشعار) — يُصدَر عند إدامة/تحديث حالة تسليم
    # تنبيه عبر قناة (queued/sent/failed/delivered). يجعل «هل وصل؟» متتبَّعاً/مدقَّقاً
    # في مجرى الأحداث الموحّد. يُستهلَك للبثّ الحيّ (WebSocket) وإعادة المحاولة.
    NOTIFICATION_DELIVERED = "notification.delivered"

    # توصية: حدث عند توليد توصية (C1/C2) — يجعلها متتبَّعة/مدقَّقة في مجرى الأحداث
    # الموحّد والإعادة، ويصل البثّ الحيّ. يُصدَر عبر outbox ضمن معاملة التخزين.
    RECOMMENDATION_CREATED = "recommendation.created"

    # أمر عمل (FOES): حدث عند تثبيت أمر عمل مُشتقّ من توصية (persist-first). يُصدَر
    # **فقط** بعد إدراج صفّ work_orders فعليّاً (لا حدث بلا تثبيت — «لا أحداث مُخترَعة»)
    # عبر outbox ضمن معاملة الكتابة، مرآةً لـRECOMMENDATION_CREATED. best-effort (غير
    # حرج): فشل الإصدار لا يكسر استجابة إنشاء أمر العمل (الصفّ مُثبَّت سلفاً).
    WORK_ORDER_CREATED = "work_order.created"

    # توزيع القرار (FOES) — تدقيق نقاط كتابة decision_dispatch (خلف علم تشغيليّ، H3).
    # تجعل سجلّ القرار/التنفيذ متتبَّعاً في مجرى الأحداث الموحّد بدل كتابة صامتة.
    DISPATCH_DECISION_RECORDED = "dispatch.decision.recorded"
    DISPATCH_EXECUTION_RECORDED = "dispatch.execution.recorded"

    # توحيد نَسَب التنفيذ (PR #396): ربط معرّف عالميّ موحّد (lin_) بمرجع قائم
    # (decision/dispatch/command/execution/outcome) **فوق** المعرّفات القائمة دون إعادة
    # تسمية — يجعل ربط السلسلة متتبَّعاً/مدقَّقاً. يُصدَر عبر outbox خلف FEATURE_UNIFIED_LINEAGE.
    LINEAGE_LINKED = "lineage.linked"

    # سلسلة النَّسَب المُدامة (Decision→Outcome→Evidence→Learning, P0-1/P0-3): إدامة
    # رأس القرار (decision_record) ونتيجته الميدانيّة (outcome_record) بمعرّف موحّد —
    # تجعل القرار وأثره متتبَّعَين/مدقَّقَين للتراكم المعرفيّ بدل حساب عابر يُنسى.
    DECISION_RECORDED = "decision.recorded"
    OUTCOME_MEASURED = "outcome.measured"

    # معايرة إقليميّة مُدارة DB-backed (البند 3): إدامة قيم معايرة مُتحقَّقة لكلّ
    # مستأجِر×منطقة بدل تعديل الكود — تجعل التغيير متتبَّعاً/مدقَّقاً في مجرى الأحداث.
    CALIBRATION_OVERRIDE_SET = "calibration.override.set"
    # سجلّ تدقيق المعايرة (v84): قيد append-only لكلّ تغيير معايرة (override_set/
    # reverted/adaptation_applied) مع لقطة القيم قبل/بعد — يجعل التغيير متتبَّعاً/مدقَّقاً.
    CALIBRATION_AUDIT_RECORDED = "calibration.audit.recorded"

    # تغطية أحداث نقاط الكتابة (إكمال CDES P0-2): تجعل تحديثات المهامّ/المزارع/جداول
    # الريّ تفاعليّة (بثّ حيّ للواجهة عبر وكيل الإشعارات) بدل مسح دوريّ.
    TASK_UPDATED = "task.updated"
    # إنشاء مهمّة (جسر الطقس→مهمّة: tasks/from-operation-plan) — يُصدِره _emit_domain_event.
    TASK_CREATED = "task.created"
    FARM_CREATED = "farm.created"
    IRRIGATION_SCHEDULE_CREATED = "irrigation.schedule.created"
    # أحداث الصمّامات (تسجيل + تغيير حالة) — لازمة لنقاط /irrigation/valves.
    IRRIGATION_VALVE_REGISTERED = "irrigation.valve.registered"
    IRRIGATION_VALVE_STATE_CHANGED = "irrigation.valve.state_changed"
    # IRR-F01 Gate B: نيّة إرسال الحجز عبر outbox القائم (dispatch_requested لا dispatched؛
    # التسليم الفعليّ للـexecution_request يتمّ عبر عامل outbox القائم + decision-service).
    IRRIGATION_RESERVATION_DISPATCH_REQUESTED = "irrigation.reservation.dispatch_requested"
    IRRIGATION_RESERVATION_DISPATCH_FAILED = "irrigation.reservation.dispatch_failed"
    # المرحلة 2: مخزون/معدّات/مرجعيّة/دورة زراعيّة.
    INVENTORY_ITEM_CREATED = "inventory.item.created"
    INVENTORY_BATCH_ADDED = "inventory.batch.added"
    EQUIPMENT_CREATED = "equipment.created"
    MAINTENANCE_LOGGED = "equipment.maintenance.logged"
    MASTER_DATA_CREATED = "master_data.created"
    CROP_ROTATION_ADDED = "crop_rotation.added"

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
    SOIL_LAB_RESULT_PUBLISHED = "soil.lab.result.published"
    WEATHER_RAIN = "weather.rain"
    MOISTURE_LOW = "weather.moisture.low"

    # AI suggestions (NOT decisions — human-in-loop)
    AI_SUGGESTION = "ai.suggestion.generated"
    AI_ANOMALY_DETECTED = "ai.anomaly.detected"

    # Supply-chain traceability (farm-to-market) — v65
    HARVEST_LOT_CREATED = "harvest.lot.created"
    CUSTODY_EVENT_RECORDED = "harvest.custody.recorded"


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
        """conn من tenant_connection (RLS مُطبَّق) أو من الـpool (توافق خلفي).

        مسار الطلب يمرّر conn دائماً (main.py يُنشئ EventBus بـconn من
        tenant_connection)، فيُطبَّق app.current_tenant. مسار الـpool احتياطيّ
        خلفيّ بلا سياق مستأجِر؛ تحت الدور المُقيَّد (NOBYPASSRLS/FORCE RLS) إن
        استُعمل خلفيّاً يحتاج دوراً خدميّاً مخصّصاً (BYPASSRLS).
        """
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
                       command_id, occurred_at, recorded_at, seq
                FROM events
                WHERE entity_type = $1 AND entity_id = $2
                ORDER BY occurred_at ASC, seq ASC
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
                    "seq": r["seq"],  # مؤشّر الترتيب الحتميّ (v63) — كاسر تعادل occurred_at
                }
                for r in rows
            ]


# ─── Idempotent consumption (processed_events dedup) ────────────

# وسم المُستهلِك الافتراضيّ في processed_events.consumer — مُستهلِك relay الـoutbox.
OUTBOX_CONSUMER_NAME: str = "outbox_relay"


def claim_is_first(insert_status: str | None) -> bool:
    """هل المطالبة (claim) هي أوّل استهلاك للحدث؟ — نقيّة، حتميّة، بلا قاعدة.

    asyncpg ``conn.execute`` يُرجع وسماً نصّيّاً مثل ``"INSERT 0 1"`` (نُسِخ صفّ واحد)
    أو ``"INSERT 0 0"`` (تعارض على الـPK ⇒ DO NOTHING، لم يُدرَج شيء). نفصل تفسير
    rowcount عن تنفيذ الـSQL كي يُختبَر offline:

      • أُدرِج صفّ (rowcount ≥ 1)  ⇒ أوّل استهلاك  ⇒ True  (طبّق الأثر الجانبيّ).
      • تعارض (rowcount = 0)      ⇒ عولِج سابقاً  ⇒ False (تخطَّ — لا أثر مزدوج).

    أيّ وسم غير مفهوم (None/خالٍ/مشوَّه) يُعامَل **محافِظاً** كأوّل استهلاك (True):
    أثر جانبيّ مُعاد (at-least-once) أأمن من ابتلاع صامت لحدث لم يُعالَج قطّ.
    """
    if not insert_status:
        return True
    try:
        count = int(str(insert_status).rsplit(" ", 1)[-1])
    except (ValueError, IndexError):
        return True
    return count >= 1


async def claim_event(conn, event_id, consumer: str = OUTBOX_CONSUMER_NAME) -> bool:
    """يُطالِب حدثاً للاستهلاك مرّةً واحدة عبر processed_events (idempotency key).

    INSERT … ON CONFLICT (event_id) DO NOTHING داخل **معاملة المُستدعي** (لا معاملة
    جديدة هنا) — كي تُثبَّت المطالبة والأثر الجانبيّ معاً أو يُرجَعا معاً (ذرّيّة).
    يُرجع True إن كانت أوّل مطالبة (طبّق الأثر) أو False إن عولِج سابقاً (تخطَّ).

    DB-less: المُستدعي يقرّر استدعاءها (المرسِل يفعل ذلك فقط حين توفّر conn حقيقيّ).
    قابلة للاختبار بـconn زائف يُرجع وسم INSERT.
    """
    status = await conn.execute(
        """
        INSERT INTO processed_events (event_id, consumer)
        VALUES ($1::uuid, $2)
        ON CONFLICT (event_id) DO NOTHING
        """,
        str(event_id),
        consumer,
    )
    return claim_is_first(status)


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

        عابر للمستأجِرين بالتصميم: لا يُضبط app.current_tenant هنا قصداً (يُرسِل
        أحداث كلّ المستأجِرين). تحت الدور المُقيَّد (sahool_app: NOBYPASSRLS, FORCE
        RLS) سيُرجع هذا صفر صفوف؛ لذا يحتاج هذا العامل دوراً خدميّاً مخصّصاً
        (BYPASSRLS) عند نشر الدور المُقيَّد — متابعة نشر، لا تغيير سلوك هنا.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # SELECT FOR UPDATE SKIP LOCKED للـconcurrent workers safety
                # بوّابة زمنيّة (TRUE backoff): صفّ فشل سابقاً لا يُعاد إلا بعد
                # انقضاء تأخيره الأسّيّ — make_interval(secs => LEAST(cap,
                # base*power(2, retry_count)))، مطابق لـoutbox_backoff_seconds.
                # صفّ لم يُحاوَل بعد (last_attempt_at IS NULL) = فوريّ (بلا تغيير).
                # SQL صرف: لا حساب لكلّ صفّ في بايثون.
                rows = await conn.fetch(
                    """
                    SELECT o.outbox_id, o.event_id, o.nats_subject, o.retry_count,
                           e.event_type, e.entity_type, e.entity_id, e.tenant_id,
                           e.payload, e.occurred_at
                    FROM event_outbox o
                    JOIN events e ON e.event_id = o.event_id
                    WHERE o.status IN ('pending', 'failed')
                      AND o.retry_count < $1
                      AND (
                            o.last_attempt_at IS NULL
                            OR o.last_attempt_at <= NOW() - make_interval(
                                secs => LEAST(
                                    $3::float8,
                                    $4::float8 * power(2, o.retry_count)
                                )
                            )
                      )
                    ORDER BY o.created_at ASC
                    LIMIT $2
                    FOR UPDATE OF o SKIP LOCKED
                    """,
                    self.max_retries,
                    self.batch_size,
                    OUTBOX_BACKOFF_MAX_SECONDS,
                    OUTBOX_BACKOFF_BASE_SECONDS,
                )

                if not rows:
                    return 0

                for row in rows:
                    await self._send_one(conn, row)

                return len(rows)

    async def _send_one(self, conn, row):
        """يرسل event واحد إلى NATS مع retry tracking + تعاضُد استهلاك (idempotent).

        التعاضُد (P1): تسليم الـoutbox at-least-once (صفّ مُرسَل قبيل تعطّل قبل وسمه
        'sent' يُعاد). لذا قبل النشر (الأثر الجانبيّ) نُطالِب الحدث عبر processed_events.

        الذرّيّة (savepoint): المطالبة + النشر + وسم 'sent' داخل معاملة متداخلة
        (conn.transaction() = SAVEPOINT داخل معاملة الدُّفعة). فشل النشر ⇒ يُرجَع
        SAVEPOINT ⇒ تُلغى المطالبة (processed_events) معاً ⇒ لا «معالَج» بلا نشر،
        ويُعاد الحدث في دورة لاحقة. تتبّع المحاولة (retry/dead-letter) يُحدَّث **بعد**
        التراجع (خارج SAVEPOINT) فيبقى مُثبَّتاً. مطالبة مُتعارِضة (عولِج سابقاً) ⇒
        نتخطّى النشر ونُجرّد الصفّ بوسمه 'sent' (لا أثر مزدوج، ولا إعادة محاولة عبثيّة).

        السجلّ الجنائيّ (v19.5-4): كلّ محاولة (نجاح/تخطٍّ/فشل) تُلحِق صفّاً في
        outbox_delivery_attempts (attempt_no = retry_count+1) داخل نفس معاملة تحديث
        الحالة (ذرّيّ)، لكن fail-safe: فشل التسجيل لا يكسر التسليم (راجع
        _record_delivery_attempt).
        """
        attempt_no = row["retry_count"] + 1
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
            async with conn.transaction():  # SAVEPOINT: مطالبة+نشر+وسم ذرّيّاً
                # المطالبة الذرّيّة أوّلاً: عولِج سابقاً (إعادة تسليم) ⇒ تخطَّ النشر.
                claimed = await claim_event(conn, row["event_id"])
                if not claimed:
                    logger.debug(
                        "event already processed (skip publish): event_id=%s outbox_id=%s",
                        row["event_id"],
                        row["outbox_id"],
                    )
                    await conn.execute(
                        """
                        UPDATE event_outbox
                        SET status = 'sent', sent_at = NOW(), last_error = NULL
                        WHERE outbox_id = $1
                        """,
                        row["outbox_id"],
                    )
                    await self._record_delivery_attempt(
                        conn, row, attempt_no=attempt_no, outcome="skipped", error=None
                    )
                    return

                await self.publish(row["nats_subject"], json.dumps(envelope).encode())
                await conn.execute(
                    """
                    UPDATE event_outbox
                    SET status = 'sent', sent_at = NOW(), last_error = NULL
                    WHERE outbox_id = $1
                    """,
                    row["outbox_id"],
                )
                await self._record_delivery_attempt(
                    conn, row, attempt_no=attempt_no, outcome="published", error=None
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
            # السجلّ الجنائيّ: صفّ محاولة فاشلة (attempt_no = new_retry المُتزايد) مع نصّ
            # الخطأ — يُثبَّت مع تحديث retry أعلاه (خارج SAVEPOINT، لا يُتراجَع عنه).
            await self._record_delivery_attempt(
                conn, row, attempt_no=new_retry, outcome="failed", error=err_msg
            )
            if new_status == "failed":
                # حدث ميّت (DLQ): استُنفدت المحاولات. تصعيد ERROR ليلتقطه الرصد/التنبيه
                # — يبقى في event_outbox (status='failed') لإعادة جدولته عبر
                # requeue_dead_letter بعد إصلاح السبب (راجع v_event_dead_letter).
                # exc_info مرّة واحدة عند النفاد (لا في كلّ محاولة) — يحفظ stack
                # trace للسبب الجذريّ دون إغراق السجلّات.
                logger.error(
                    "DEAD_LETTER outbox_id=%s event=%s بعد %s محاولة: %s",
                    row["outbox_id"],
                    row["event_type"],
                    self.max_retries,
                    err_msg,
                    exc_info=True,
                )
            else:
                logger.warning(f"outbox send failed ({new_retry}/{self.max_retries}): {err_msg}")

    async def _record_delivery_attempt(
        self, conn, row, *, attempt_no: int, outcome: str, error: str | None
    ) -> None:
        """يُلحِق صفّاً في outbox_delivery_attempts (سجلّ جنائيّ append-only، v19.5-4).

        صفّ لكلّ محاولة تسليم فردية (طابع زمنيّ/موضوع/نتيجة/خطأ) — يكمّل حالة
        event_outbox المُجمَّعة (retry_count + last_error الواحد) بأثر لا يُدهَس؛ فبعد
        المحاولة #3 يبقى خطأ #2 مرئيّاً للتشخيص (DLQ).

        ذرّيّ لكن fail-safe: الإدراج داخل SAVEPOINT متداخل (conn.transaction())، فإن
        فشل (مثلاً قبل تطبيق هجرة v140) يُرجَع SAVEPOINT وحده — لا يُفسِد معاملة
        التسليم (وسم 'sent'/retry يبقى مُثبَّتاً) ولا يُرفَع الاستثناء. التسجيل مساعِد
        رصديّ، فشله لا يُبطل تسليماً تمّ فعلاً.
        """
        tenant_id = row["tenant_id"]
        try:
            async with conn.transaction():  # SAVEPOINT معزول: فشل التسجيل لا يكسر التسليم
                await conn.execute(
                    """
                    INSERT INTO outbox_delivery_attempts
                        (outbox_id, tenant_id, attempt_no, subject, outcome, error)
                    VALUES ($1, $2::uuid, $3, $4, $5, $6)
                    """,
                    row["outbox_id"],
                    str(tenant_id) if tenant_id is not None else None,
                    attempt_no,
                    row["nats_subject"],
                    outcome,
                    error,
                )
        except Exception as log_exc:  # noqa: BLE001 — رصديّ فقط، لا يُبطل التسليم
            logger.warning(
                "outbox delivery-attempt log insert failed (non-fatal) outbox_id=%s: %s",
                row["outbox_id"],
                log_exc,
            )

    # ─── Dead-letter (DLQ) inspect / requeue ────────────────────

    async def list_dead_letter(self, conn, limit: int = 500) -> dict[str, Any]:
        """يُحصي الصفوف الميّتة (status='failed' AND retry_count>=max) ويُرجع عيّنة.

        صفّ ميّت = استُنفدت محاولاته فلم يعد SELECT الرئيسيّ يلتقطه. الـSQL أدنويّ
        (فلتر + ترتيب + حدّ)؛ تشكيل الخرج عبر dead_letter_summary النقيّة.
        """
        recs = await conn.fetch(
            """
            SELECT outbox_id, event_id, nats_subject, retry_count,
                   last_error, last_attempt_at
            FROM event_outbox
            WHERE status = 'failed' AND retry_count >= $1
            ORDER BY last_attempt_at DESC NULLS LAST
            LIMIT $2
            """,
            self.max_retries,
            limit,
        )
        return dead_letter_summary([dict(r) for r in recs])

    async def requeue_dead_letter(self, conn, outbox_id: int | None = None) -> int:
        """يعيد جدولة الصفوف الميّتة → pending (retry_count=0, last_attempt_at=NULL).

        ``outbox_id`` محدّد ⇒ صفّ واحد، أو None ⇒ كلّ الصفوف الميّتة. يُرجع عدد
        الصفوف المُعاد جدولتها كي يلتقطها العامل في الدورة التالية فوراً.
        """
        if outbox_id is not None:
            status = await conn.execute(
                """
                UPDATE event_outbox
                SET status = 'pending', retry_count = 0,
                    last_attempt_at = NULL, last_error = NULL
                WHERE outbox_id = $1 AND status = 'failed' AND retry_count >= $2
                """,
                outbox_id,
                self.max_retries,
            )
        else:
            status = await conn.execute(
                """
                UPDATE event_outbox
                SET status = 'pending', retry_count = 0,
                    last_attempt_at = NULL, last_error = NULL
                WHERE status = 'failed' AND retry_count >= $1
                """,
                self.max_retries,
            )
        # asyncpg execute يُرجع نصّاً مثل "UPDATE 3" — استخرج العدد.
        try:
            return int(str(status).rsplit(" ", 1)[-1])
        except (ValueError, IndexError):
            return 0
