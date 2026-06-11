"""
services/sahool-platform/api/data_lineage.py — Unified Data Lineage

المرجع: المراجعة الخارجيّة:
   "لم أجد طبقة قوية لـ:
      - provenance tracking
      - immutable event chain
      - replayable decisions
      - audit-grade telemetry"

✅ الادّعاء جزئيّاً صحيح. لدينا المُكوّنات لكن غير مُوحَّدة:
   - commands table        (intent)
   - events table          (facts)
   - ExecutionJournal      (tool invocations)
   - field_lifecycle_transitions  (state machine)
   - field_revisions       (geometry history — mobile)

هذا الملف يجمعها في endpoint واحد:
   GET /lineage/entity/{type}/{id}  → كل ما حدث على هذا الـentity

الفائدة الفعليّة (ليست fancy "Causality Sourced System"):
   - audit: "من أنشأ هذا الحقل؟ متى؟"
   - debugging: "لماذا الـrecommendation كان N=80؟"
   - compliance: "أرني سجلّ كامل لكل القرارات على هذا الحقل"

ما لا يفعله:
   ✗ ML pattern detection
   ✗ "causal AI reasoning"
   ✗ time-travel "consciousness"
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager as _asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


# ─── Types ──────────────────────────────────────────────────────


class LineageSourceType(str, Enum):  # noqa: UP042 (intentional str-mixin for JSON/Pydantic value serialization)
    """من أين جاءت كل entry في الـlineage."""

    COMMAND = "command"  # commands table
    EVENT = "event"  # events table
    LIFECYCLE = "lifecycle_transition"  # field_lifecycle_transitions
    JOURNAL = "execution_journal"  # tool invocations
    TRUEUP = "trueup_calibration"  # trueup_calibrations


@dataclass
class LineageEntry:
    """نقطة واحدة في sequence الـlineage."""

    timestamp: str
    source_type: LineageSourceType
    source_id: str  # primary key في الجدول المصدر
    actor_id: str | None
    action: str  # human-readable
    payload: dict[str, Any]
    related_command_id: str | None = None
    summary_ar: str = ""


@dataclass
class EntityLineage:
    """كل ما حدث على entity (موحّد عبر الـsources)."""

    entity_type: str
    entity_id: str
    total_entries: int
    earliest_at: str | None
    latest_at: str | None
    entries: list[LineageEntry]

    # Summary stats
    commands_count: int = 0
    events_count: int = 0
    lifecycle_transitions: int = 0
    journal_invocations: int = 0
    trueup_applications: int = 0


# ─── Arabic action summaries ────────────────────────────────────

_ACTION_SUMMARIES_AR = {
    # Command types
    "field.create": "إنشاء حقل",
    "field.update": "تحديث حقل",
    "field.delete": "حذف حقل",
    "operation.planting.start": "بدء البذر",
    "operation.harvest.complete": "اكتمال الحصاد",
    "operation.irrigation.start": "بدء الري",
    "field.advance_stage": "تقدّم المرحلة",
    "prescription.applied": "تطبيق وصفة",
    "walk_plan.generated": "توليد خطة مشي",
    "trueup.apply": "معايرة الإنتاج",
}


def _summarize_action(action: str, payload: dict[str, Any]) -> str:
    """ولّد ملخّص عربي قصير."""
    base = _ACTION_SUMMARIES_AR.get(action, action)

    # إضافات سياقيّة
    if "water_m3" in payload:
        return f"{base} ({payload['water_m3']} م³)"
    if "k_new" in payload:
        return f"{base} (k={payload['k_new']:.3f})"
    if "to_stage" in payload:
        return f"{base} → {payload['to_stage']}"
    if "area_ha" in payload:
        return f"{base} ({payload['area_ha']} هكتار)"
    return base


class _ReadOnlyConn:
    """وكيل اتّصال يمنع الكتابة (Source-of-Truth enforcement، مراجعة #3).

    يلفّ asyncpg connection ويفحص كلّ استعلام: fetch/fetchrow/fetchval مسموحة
    (قراءة)؛ execute بكتابة (INSERT/UPDATE/DELETE) يُرفَض. يضمن أنّ المجمّع
    لا يصبح writable صامتاً (projection لا يكتب حقيقة)."""

    _WRITE = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "MERGE")

    def __init__(self, conn):
        self._c = conn

    @staticmethod
    def _check(sql):
        if sql.lstrip()[:12].upper().startswith(_ReadOnlyConn._WRITE):
            raise RuntimeError("المجمّع طبقة قراءة فقط — الكتابة عبر command_store/event_bus")

    async def fetch(self, sql, *a, **k):
        self._check(sql)
        return await self._c.fetch(sql, *a, **k)

    async def fetchrow(self, sql, *a, **k):
        self._check(sql)
        return await self._c.fetchrow(sql, *a, **k)

    async def fetchval(self, sql, *a, **k):
        self._check(sql)
        return await self._c.fetchval(sql, *a, **k)

    async def execute(self, sql, *a, **k):
        self._check(sql)
        return await self._c.execute(sql, *a, **k)


# ─── Lineage assembler ──────────────────────────────────────────


class LineageAssembler:
    """
    يجمع entries من ٥ مصادر مختلفة ويرتّبها زمنياً.

    Usage:
        assembler = LineageAssembler(pool)
        lineage = await assembler.get_entity_lineage("field", field_id)
    """

    def __init__(self, pool: asyncpg.Pool, conn=None):
        import asyncpg as _ap  # noqa: F401

        self.pool = pool
        # conn اختياري: لو مُرّر (من tenant_connection) يُستخدم مباشرةً فيُطبَّق
        # RLS؛ وإلّا يُكتسب من الـpool (توافق خلفي).
        self._conn = conn

    # Source-of-Truth enforcement (مراجعة #3): الـassembler طبقة قراءة فقط —
    # لا يملك الحقيقة، يجمّعها. هذا الحارس يفرض ذلك runtime: أيّ محاولة كتابة
    # عبره تفشل بصوت عالٍ (لا انحراف صامت يجعل projection يكتب حقيقة).
    _READ_ONLY = True

    @staticmethod
    def _guard_read_only(sql: str) -> None:
        upper = sql.lstrip()[:12].upper()
        if upper.startswith(("INSERT", "UPDATE", "DELETE", "TRUNCATE", "MERGE")):
            raise RuntimeError(
                "LineageAssembler طبقة قراءة فقط — لا يكتب حقيقة (Source of Truth). "
                "الكتابة تتمّ عبر command_store/event_bus لا عبر المجمّع."
            )

    @_asynccontextmanager
    async def _acquire(self):
        if self._conn is not None:
            yield _ReadOnlyConn(self._conn)
        else:
            async with self.pool.acquire() as c:
                yield _ReadOnlyConn(c)

    async def get_entity_lineage(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 500,
    ) -> EntityLineage:
        """يجمع lineage كامل للـentity."""

        entries: list[LineageEntry] = []

        async with self._acquire() as conn:
            # ١. Commands المتعلّقة (بـpayload contains entity_id)
            cmd_rows = await conn.fetch(
                """
                SELECT command_id, command_type, actor_id, payload, source,
                       status, created_at, completed_at, error
                FROM commands
                WHERE payload->>'field_id' = $1
                   OR payload->>'entity_id' = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                entity_id,
                limit,
            )

            for r in cmd_rows:
                payload = r["payload"] if isinstance(r["payload"], dict) else {}
                entries.append(
                    LineageEntry(
                        timestamp=r["created_at"].isoformat() if r["created_at"] else "",
                        source_type=LineageSourceType.COMMAND,
                        source_id=str(r["command_id"]),
                        actor_id=r["actor_id"],
                        action=r["command_type"],
                        payload=payload,
                        related_command_id=str(r["command_id"]),
                        summary_ar=f"[أمر] {_summarize_action(r['command_type'], payload)}"
                        + (f" — {r['status']}" if r["status"] != "succeeded" else ""),
                    )
                )

            # ٢. Events
            try:
                event_rows = await conn.fetch(
                    """
                    SELECT event_id, event_type, actor_id, command_id, payload,
                           source, occurred_at
                    FROM events
                    WHERE entity_type = $1 AND entity_id = $2
                    ORDER BY occurred_at DESC
                    LIMIT $3
                    """,
                    entity_type,
                    entity_id,  # نصّيّ منذ v18 (معرّفات الحقول نصّيّة)
                    limit,
                )
                for r in event_rows:
                    payload = r["payload"] if isinstance(r["payload"], dict) else {}
                    entries.append(
                        LineageEntry(
                            timestamp=r["occurred_at"].isoformat() if r["occurred_at"] else "",
                            source_type=LineageSourceType.EVENT,
                            source_id=str(r["event_id"]),
                            actor_id=r["actor_id"],
                            action=r["event_type"],
                            payload=payload,
                            related_command_id=str(r["command_id"]) if r["command_id"] else None,
                            summary_ar=f"[حدث] {_summarize_action(r['event_type'], payload)}",
                        )
                    )
            except Exception as e:
                # events table قد لا تكون موجودة (لو v11 migration لم يُطبَّق بعد)
                logger.debug(f"lineage: events table unavailable: {e}")

            # ٣. Lifecycle transitions (لو entity حقل)
            if entity_type == "field":
                try:
                    lc_rows = await conn.fetch(
                        """
                        SELECT t.transition_id, t.from_stage, t.to_stage,
                               t.transitioned_at, t.changed_by, t.command_id, t.reason
                        FROM field_lifecycle_transitions t
                        JOIN field_lifecycle l ON l.lifecycle_id = t.lifecycle_id
                        WHERE l.field_id = $1
                        ORDER BY t.transitioned_at DESC
                        LIMIT $2
                        """,
                        entity_id,  # نصّيّ منذ v18 (معرّفات الحقول نصّيّة)
                        limit,
                    )
                    for r in lc_rows:
                        entries.append(
                            LineageEntry(
                                timestamp=r["transitioned_at"].isoformat()
                                if r["transitioned_at"]
                                else "",
                                source_type=LineageSourceType.LIFECYCLE,
                                source_id=str(r["transition_id"]),
                                actor_id=r["changed_by"],
                                action=f"lifecycle: {r['from_stage'] or '∅'} → {r['to_stage']}",
                                payload={
                                    "from": r["from_stage"],
                                    "to": r["to_stage"],
                                    "reason": r["reason"],
                                },
                                related_command_id=str(r["command_id"])
                                if r["command_id"]
                                else None,
                                summary_ar=f"[مرحلة] {r['from_stage'] or '—'} → {r['to_stage']}",
                            )
                        )
                except Exception as e:
                    logger.debug(f"lineage: optional source unavailable: {e}")

            # ٤. TrueUp calibrations
            if entity_type == "field":
                try:
                    tu_rows = await conn.fetch(
                        """
                        SELECT calibration_id, operation_id, k_factor,
                               actual_weight_kg, measured_weight_kg,
                               error_pct, applied_by, applied_at, command_id
                        FROM trueup_calibrations
                        WHERE field_id = $1
                        ORDER BY applied_at DESC
                        LIMIT $2
                        """,
                        entity_id,  # نصّيّ منذ v18 (معرّفات الحقول نصّيّة)
                        limit,
                    )
                    for r in tu_rows:
                        entries.append(
                            LineageEntry(
                                timestamp=r["applied_at"].isoformat() if r["applied_at"] else "",
                                source_type=LineageSourceType.TRUEUP,
                                source_id=str(r["calibration_id"]),
                                actor_id=r["applied_by"],
                                action="trueup.applied",
                                payload={
                                    "k": float(r["k_factor"]),
                                    "actual_kg": float(r["actual_weight_kg"]),
                                    "measured_kg": float(r["measured_weight_kg"]),
                                    "error_pct": float(r["error_pct"]) if r["error_pct"] else 0,
                                },
                                related_command_id=str(r["command_id"])
                                if r["command_id"]
                                else None,
                                summary_ar=f"[معايرة] k={float(r['k_factor']):.3f} "
                                f"(خطأ {float(r['error_pct'] or 0):.1f}%)",
                            )
                        )
                except Exception as e:
                    logger.debug(f"lineage: optional source unavailable: {e}")

        # ٥. ترتيب نهائي (الأحدث أوّلاً)
        entries.sort(key=lambda e: e.timestamp, reverse=True)

        # احسب الإحصاءات
        counts = {
            LineageSourceType.COMMAND: 0,
            LineageSourceType.EVENT: 0,
            LineageSourceType.LIFECYCLE: 0,
            LineageSourceType.JOURNAL: 0,
            LineageSourceType.TRUEUP: 0,
        }
        for e in entries:
            counts[e.source_type] = counts.get(e.source_type, 0) + 1

        return EntityLineage(
            entity_type=entity_type,
            entity_id=entity_id,
            total_entries=len(entries),
            earliest_at=entries[-1].timestamp if entries else None,
            latest_at=entries[0].timestamp if entries else None,
            entries=entries[:limit],
            commands_count=counts[LineageSourceType.COMMAND],
            events_count=counts[LineageSourceType.EVENT],
            lifecycle_transitions=counts[LineageSourceType.LIFECYCLE],
            journal_invocations=counts[LineageSourceType.JOURNAL],
            trueup_applications=counts[LineageSourceType.TRUEUP],
        )

    async def get_command_chain(self, command_id: str) -> dict[str, Any]:
        """
        يأخذ command_id ويُرجع كلّ ما تولّد عنه:
            - الـcommand نفسه
            - الـevents التي ولّدها
            - الـlifecycle transitions
            - الـtrueup applications

        مفيد للـdebugging: "ماذا حدث بعد هذا الـcommand؟"
        """
        import uuid as _u

        async with self._acquire() as conn:
            cmd = await conn.fetchrow(
                "SELECT * FROM commands WHERE command_id = $1",
                _u.UUID(command_id),
            )
            if not cmd:
                return {"command_id": command_id, "found": False}

            events = await conn.fetch(
                """
                SELECT event_id, event_type, occurred_at, payload
                FROM events WHERE command_id = $1
                ORDER BY occurred_at
                """,
                _u.UUID(command_id),
            )

            transitions = await conn.fetch(
                """
                SELECT transition_id, from_stage, to_stage, transitioned_at
                FROM field_lifecycle_transitions WHERE command_id = $1
                """,
                _u.UUID(command_id),
            )

        return {
            "command_id": command_id,
            "found": True,
            "command": {
                "type": cmd["command_type"],
                "status": cmd["status"],
                "actor_id": cmd["actor_id"],
                "created_at": cmd["created_at"].isoformat() if cmd["created_at"] else None,
            },
            "triggered_events": [
                {
                    "event_id": str(e["event_id"]),
                    "event_type": e["event_type"],
                    "occurred_at": e["occurred_at"].isoformat() if e["occurred_at"] else None,
                }
                for e in events
            ],
            "triggered_transitions": [
                {
                    "transition_id": str(t["transition_id"]),
                    "from_stage": t["from_stage"],
                    "to_stage": t["to_stage"],
                    "at": t["transitioned_at"].isoformat() if t["transitioned_at"] else None,
                }
                for t in transitions
            ],
        }
