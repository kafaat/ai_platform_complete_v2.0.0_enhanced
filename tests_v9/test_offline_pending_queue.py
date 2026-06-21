"""اختبارات وحدة: الطابور المعلّق الدائم + توسيع OperationKind (Stage A P1/P2).

كلّها unit (بلا قاعدة/شبكة): تستخدم conn مزيّف (fake) يسجّل SQL/الوسائط، فتتحقّق
من منطق الإدامة (enqueue/fetch/mark + idempotency) دون Postgres حقيقي، ومن أنّ
المسار الذاكريّ يبقى مرجعاً حين لا قاعدة (DATABASE_URL غير مضبوط)، ومن قبول
أعضاء OperationKind الجديدة.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

from core.offline_first import (  # noqa: E402
    OfflineQueue,
    OperationKind,
    PendingOperation,
    record_operation_offline,
)

# ─── conn مزيّف (يحاكي asyncpg.Connection بما يكفي للاختبار) ──────────


class _FakeConn:
    """conn async مزيّف: يسجّل كلّ execute/fetch ويُحاكي ON CONFLICT/UPDATE.

    يحمل «جدولاً» في الذاكرة (dict op_id→row) ليتحقّق idempotency منطقيّاً، لا
    نصّيّاً فقط. لا RLS هنا (يُختبَر في integration test_db_wiring).
    """

    def __init__(self):
        self.executed: list[tuple[str, tuple]] = []
        self.rows: dict[str, dict] = {}

    async def execute(self, sql: str, *args):
        self.executed.append((sql, args))
        s = " ".join(sql.split())
        if s.startswith("INSERT INTO offline_pending_ops"):
            op_id = args[0]
            # ON CONFLICT DO NOTHING ⇒ لا نكتب إن كان موجوداً
            if op_id not in self.rows:
                self.rows[op_id] = {
                    "op_id": op_id,
                    "tenant_id": args[1],
                    "user_id": args[2],
                    "op_kind": args[3],
                    "payload": args[4],
                    "status": "pending",
                    "created_at": args[5],
                    "processed_at": None,
                    "attempts": 0,
                    "last_error": None,
                }
            return "INSERT 0 1"
        if s.startswith("UPDATE offline_pending_ops SET status = 'processed'"):
            op_id = args[0]
            row = self.rows.get(op_id)
            if row and row["status"] == "pending":
                row["status"] = "processed"
                row["processed_at"] = "NOW"
            return "UPDATE 1"
        if s.startswith("UPDATE offline_pending_ops SET attempts = attempts + 1"):
            op_id, error = args[0], args[1]
            row = self.rows.get(op_id)
            if row and row["status"] == "pending":
                row["attempts"] += 1
                row["last_error"] = error
            return "UPDATE 1"
        return "OK"

    async def fetch(self, sql: str, *args):
        s = " ".join(sql.split())
        if "FROM offline_pending_ops" in s and "status = 'pending'" in s:
            pend = [r for r in self.rows.values() if r["status"] == "pending"]
            pend.sort(key=lambda r: r["created_at"])
            limit = args[0] if args else len(pend)
            return pend[:limit]
        return []

    async def fetchrow(self, sql: str, *args):
        return None


def _make_op(op_id="11111111-1111-1111-1111-111111111111", kind=None, tenant="t-1"):
    return PendingOperation(
        op_id=op_id,
        tenant_id=tenant,
        user_id="u1",
        kind=kind or OperationKind.OBSERVATION_CREATE,
        payload={"field_id": "f-1", "note": "ملاحظة"},
        created_at="2026-06-20T10:00:00",
    )


def _load_pending_db():
    """يحمّل وحدة offline_pending_db (تحت services/sahool-platform/api)."""
    import importlib

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform/api"))
    return importlib.import_module("offline_pending_db")


# ─── 1) منطق الإدامة (durable path) عبر conn مزيّف ───────────────────


class TestDurableEnqueueDequeue:
    def test_enqueue_writes_row(self):
        opdb = _load_pending_db()
        conn = _FakeConn()
        op = _make_op()
        ok = asyncio.run(opdb.enqueue_pending(conn, op=op, tenant_id="t-1"))
        assert ok is True
        assert op.op_id in conn.rows
        row = conn.rows[op.op_id]
        assert row["status"] == "pending"
        assert row["op_kind"] == "observation_create"
        # payload يُسلسَل JSON
        assert json.loads(row["payload"]) == {"field_id": "f-1", "note": "ملاحظة"}

    def test_enqueue_idempotent_on_op_id(self):
        opdb = _load_pending_db()
        conn = _FakeConn()
        op = _make_op()
        asyncio.run(opdb.enqueue_pending(conn, op=op, tenant_id="t-1"))
        asyncio.run(opdb.enqueue_pending(conn, op=op, tenant_id="t-1"))
        # ON CONFLICT DO NOTHING ⇒ صفّ واحد فقط
        assert list(conn.rows).count(op.op_id) == 1
        assert len(conn.rows) == 1

    def test_fetch_pending_fifo(self):
        opdb = _load_pending_db()
        conn = _FakeConn()
        a = _make_op(op_id="aaaa", tenant="t-1")
        a.created_at = "2026-06-20T09:00:00"
        b = _make_op(op_id="bbbb", tenant="t-1")
        b.created_at = "2026-06-20T11:00:00"
        asyncio.run(opdb.enqueue_pending(conn, op=b, tenant_id="t-1"))
        asyncio.run(opdb.enqueue_pending(conn, op=a, tenant_id="t-1"))
        rows = asyncio.run(opdb.fetch_pending(conn, limit=10))
        assert [r["op_id"] for r in rows] == ["aaaa", "bbbb"]  # ترتيب الإنشاء

    def test_mark_processed_then_not_in_pending(self):
        opdb = _load_pending_db()
        conn = _FakeConn()
        op = _make_op()
        asyncio.run(opdb.enqueue_pending(conn, op=op, tenant_id="t-1"))
        asyncio.run(opdb.mark_processed(conn, op_id=op.op_id))
        rows = asyncio.run(opdb.fetch_pending(conn))
        assert rows == []
        assert conn.rows[op.op_id]["status"] == "processed"

    def test_mark_processed_idempotent(self):
        opdb = _load_pending_db()
        conn = _FakeConn()
        op = _make_op()
        asyncio.run(opdb.enqueue_pending(conn, op=op, tenant_id="t-1"))
        asyncio.run(opdb.mark_processed(conn, op_id=op.op_id))
        first_ts = conn.rows[op.op_id]["processed_at"]
        # إعادة الاستدعاء لا تُغيّر شيئاً (الشرط status='pending')
        asyncio.run(opdb.mark_processed(conn, op_id=op.op_id))
        assert conn.rows[op.op_id]["processed_at"] == first_ts

    def test_mark_failed_increments_attempts_keeps_pending(self):
        opdb = _load_pending_db()
        conn = _FakeConn()
        op = _make_op()
        asyncio.run(opdb.enqueue_pending(conn, op=op, tenant_id="t-1"))
        asyncio.run(opdb.mark_failed(conn, op_id=op.op_id, error="db down"))
        row = conn.rows[op.op_id]
        assert row["attempts"] == 1
        assert row["last_error"] == "db down"
        assert row["status"] == "pending"  # تبقى للمحاولة لاحقاً
        # ما تزال ضمن المعلّقة
        assert [r["op_id"] for r in asyncio.run(opdb.fetch_pending(conn))] == [op.op_id]


# ─── 2) الارتداد الذاكريّ حين لا قاعدة (DB-less) ─────────────────────


class TestInMemoryFallback:
    def test_persist_best_effort_noop_without_db(self):
        """بلا main/قاعدة ⇒ persist_pending_best_effort = False (لا استثناء)."""
        opdb = _load_pending_db()
        op = _make_op()
        # لا api.main محمّل في بيئة الوحدة ⇒ الاستيراد الكسول يفشل بأمان ⇒ False
        result = asyncio.run(opdb.persist_pending_best_effort(op, user=object()))
        assert result is False

    def test_in_memory_queue_still_records_without_db(self):
        """record_operation_offline يبقى يعمل ذاكريّاً (مرجع الدورة الجارية)."""
        q = OfflineQueue()
        op = record_operation_offline(
            q,
            tenant_id="t-1",
            user_id="u1",
            kind=OperationKind.OBSERVATION_CREATE,
            payload={"x": 1},
        )
        assert q.total_pending("t-1") == 1
        assert op.op_id


# ─── 3) توسيع OperationKind (المسار P2) ──────────────────────────────


class TestOperationKindExpansion:
    NEW_VALUES = {
        "task_update",
        "decision_record",
        "outcome_record",
        "irrigation_plan",
        "harvest_lot_create",
        "recommendation_outcome",
        "soil_lab_test",
        "photo_upload",
    }
    OLD_VALUES = {
        "observation_create",
        "activity_complete",
        "activity_skip",
        "recommendation_request",
        "calibration_record",
    }

    def test_old_values_preserved(self):
        present = {k.value for k in OperationKind}
        assert self.OLD_VALUES <= present, "قيمة أصليّة فُقدت — كسر للعقد"

    def test_new_values_accepted(self):
        present = {k.value for k in OperationKind}
        assert self.NEW_VALUES <= present
        # تُبنى من النصّ (كما يفعل المسار /api/v1/sync)
        for v in self.NEW_VALUES:
            assert OperationKind(v).value == v

    def test_unknown_value_still_rejected(self):
        with pytest.raises(ValueError):
            OperationKind("definitely_not_a_kind")

    def test_new_kind_records_in_memory(self):
        q = OfflineQueue()
        op = record_operation_offline(
            q,
            tenant_id="t-1",
            user_id="u1",
            kind=OperationKind.HARVEST_LOT_CREATE,
            payload={"lot": "L-1"},
        )
        assert op.kind is OperationKind.HARVEST_LOT_CREATE
        assert q.total_pending("t-1") == 1
