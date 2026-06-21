"""اختبارات سلوكيّة نقيّة لنواة offline-first (الميزة الفارقة لسهول).

تُكمّل ولا تكرّر services/sahool-platform/tests/test_offline_first.py:
تركّز على حقول PendingOperation وتعداد OperationKind/SyncStatus،
آليّة detect_superseded المباشرة وترتيبها، تفاصيل mark_status
(القيمة المُرجَعة والحقول الجانبيّة)، retention في clear_synced،
peek_pending limit/filtering، enqueue عند الحدّ، reset، ConnectivityState،
ورسائل reason_ar في SyncResult. كلّها in-memory، بلا DB ولا شبكة.
"""

import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

from core.offline_first import (  # noqa: E402
    ConnectivityState,
    OfflineQueue,
    OperationKind,
    PendingOperation,
    SyncResult,
    SyncStatus,
    apply_supersession,
    detect_superseded,
    queue_summary,
    record_operation_offline,
    sync_cycle,
)


def _op(
    op_id,
    *,
    tenant="tnt_A",
    kind=OperationKind.OBSERVATION_CREATE,
    payload=None,
    status=SyncStatus.QUEUED,
):
    return PendingOperation(
        op_id=op_id,
        tenant_id=tenant,
        user_id="u1",
        kind=kind,
        payload=payload if payload is not None else {},
        created_at="2026-06-16T00:00:00",
        status=status,
    )


# ─── تعداد القيم (Enum contracts) ────────────────────────────────


class TestEnumValues:
    def test_operation_kind_string_values(self):
        assert OperationKind.OBSERVATION_CREATE.value == "observation_create"
        assert OperationKind.ACTIVITY_COMPLETE.value == "activity_complete"
        assert OperationKind.ACTIVITY_SKIP.value == "activity_skip"
        assert OperationKind.RECOMMENDATION_REQUEST.value == "recommendation_request"
        assert OperationKind.CALIBRATION_RECORD.value == "calibration_record"

    def test_operation_kind_is_str_enum(self):
        # StrEnum: القيمة == نصّها (مهمّ للتسلسل JSON)
        assert OperationKind.ACTIVITY_SKIP == "activity_skip"
        assert isinstance(OperationKind.ACTIVITY_SKIP.value, str)

    def test_operation_kind_membership_complete(self):
        present = {k.value for k in OperationKind}
        # القيم الأصليّة محفوظة (عقد ثابت — لا كسر للبيانات المُخزّنة).
        assert {
            "observation_create",
            "activity_complete",
            "activity_skip",
            "recommendation_request",
            "calibration_record",
        } <= present
        # توسيع Stage A P2: عمليّات mutating أخرى يُنشئها العميل offline.
        assert {
            "task_update",
            "decision_record",
            "outcome_record",
            "irrigation_plan",
            "harvest_lot_create",
            "recommendation_outcome",
            "soil_lab_test",
            "photo_upload",
        } <= present

    def test_sync_status_values(self):
        assert SyncStatus.QUEUED.value == "queued"
        assert SyncStatus.SYNCING.value == "syncing"
        assert SyncStatus.SYNCED.value == "synced"
        assert SyncStatus.FAILED.value == "failed"
        assert SyncStatus.SUPERSEDED.value == "superseded"
        assert SyncStatus.CONFLICTED.value == "conflicted"

    def test_sync_status_is_str_enum(self):
        assert SyncStatus.QUEUED == "queued"


# ─── حقول PendingOperation الافتراضيّة ───────────────────────────


class TestPendingOperationFields:
    def test_defaults_on_construction(self):
        op = _op("op1")
        assert op.status == SyncStatus.QUEUED
        assert op.retry_count == 0
        assert op.last_attempt_at is None
        assert op.last_error is None
        assert op.synced_at is None
        assert op.conflict_with is None

    def test_explicit_fields_preserved(self):
        op = PendingOperation(
            op_id="x",
            tenant_id="tnt_A",
            kind=OperationKind.CALIBRATION_RECORD,
            payload={"k": "v"},
            created_at="2026-06-16T00:00:00",
            user_id="farmer_7",
        )
        assert op.user_id == "farmer_7"
        assert op.kind == OperationKind.CALIBRATION_RECORD
        assert op.payload == {"k": "v"}


# ─── detect_superseded: المنطق النقيّ المباشر ────────────────────


class TestDetectSupersededPure:
    def test_returns_old_new_pair_order(self):
        # المُرجَع (op_id_old, op_id_new): الأقدم أوّلاً
        ops = [
            _op(
                "old",
                payload={"field_id": "f1", "activity_id": "a1"},
                kind=OperationKind.ACTIVITY_COMPLETE,
            ),
            _op(
                "new",
                payload={"field_id": "f1", "activity_id": "a1"},
                kind=OperationKind.ACTIVITY_COMPLETE,
            ),
        ]
        pairs = detect_superseded(ops)
        assert pairs == [("old", "new")]

    def test_observable_id_used_as_entity_key(self):
        # observation: المفتاح يستخدم observable_id حين لا activity_id
        ops = [
            _op("o1", payload={"field_id": "f1", "observable_id": "ndvi"}),
            _op("o2", payload={"field_id": "f1", "observable_id": "ndvi"}),
        ]
        pairs = detect_superseded(ops)
        assert pairs == [("o1", "o2")]

    def test_different_observable_not_superseded(self):
        ops = [
            _op("o1", payload={"field_id": "f1", "observable_id": "ndvi"}),
            _op("o2", payload={"field_id": "f1", "observable_id": "ndmi"}),
        ]
        assert detect_superseded(ops) == []

    def test_different_kind_not_superseded(self):
        # نفس field/entity لكن نوع مختلف → لا تضارب
        ops = [
            _op(
                "a",
                payload={"field_id": "f1", "activity_id": "a1"},
                kind=OperationKind.ACTIVITY_COMPLETE,
            ),
            _op(
                "b",
                payload={"field_id": "f1", "activity_id": "a1"},
                kind=OperationKind.ACTIVITY_SKIP,
            ),
        ]
        assert detect_superseded(ops) == []

    def test_missing_key_field_skipped(self):
        # None في المفتاح (لا field_id) → تُتجاهل، لا تضارب
        ops = [
            _op("o1", payload={"observable_id": "ndvi"}),
            _op("o2", payload={"observable_id": "ndvi"}),
        ]
        assert detect_superseded(ops) == []

    def test_non_queued_ops_ignored(self):
        # العمليّات غير QUEUED لا تُحسب في كشف التضارب
        ops = [
            _op(
                "o1", payload={"field_id": "f1", "observable_id": "ndvi"}, status=SyncStatus.SYNCED
            ),
            _op("o2", payload={"field_id": "f1", "observable_id": "ndvi"}),
        ]
        assert detect_superseded(ops) == []

    def test_three_same_entity_chains_pairs(self):
        # ثلاث عمليّات على نفس الكيان → زوجان (1→2, 2→3)
        ops = [
            _op("o1", payload={"field_id": "f1", "observable_id": "ndvi"}),
            _op("o2", payload={"field_id": "f1", "observable_id": "ndvi"}),
            _op("o3", payload={"field_id": "f1", "observable_id": "ndvi"}),
        ]
        assert detect_superseded(ops) == [("o1", "o2"), ("o2", "o3")]


# ─── mark_status: القيمة المُرجَعة والحقول الجانبيّة ──────────────


class TestMarkStatusDetails:
    def test_returns_false_for_unknown_op(self):
        q = OfflineQueue()
        q.enqueue(_op("real"))
        assert q.mark_status("tnt_A", "ghost", SyncStatus.SYNCED) is False

    def test_returns_false_for_unknown_tenant(self):
        q = OfflineQueue()
        assert q.mark_status("no_tenant", "x", SyncStatus.SYNCED) is False

    def test_error_sets_field_and_increments_retry(self):
        q = OfflineQueue()
        q.enqueue(_op("op1"))
        assert q.mark_status("tnt_A", "op1", SyncStatus.FAILED, error="boom") is True
        op = list(q._queues["tnt_A"])[0]
        assert op.last_error == "boom"
        assert op.retry_count == 1
        assert op.last_attempt_at is not None

    def test_no_error_does_not_increment_retry(self):
        q = OfflineQueue()
        q.enqueue(_op("op1"))
        q.mark_status("tnt_A", "op1", SyncStatus.SYNCING)
        op = list(q._queues["tnt_A"])[0]
        assert op.retry_count == 0
        assert op.last_error is None
        assert op.last_attempt_at is not None  # يُضبط دائماً

    def test_synced_sets_synced_at(self):
        q = OfflineQueue()
        q.enqueue(_op("op1"))
        q.mark_status("tnt_A", "op1", SyncStatus.SYNCED)
        op = list(q._queues["tnt_A"])[0]
        assert op.synced_at is not None


# ─── peek_pending: limit وتصفية الحالة ───────────────────────────


class TestPeekPending:
    def test_unknown_tenant_returns_empty_list(self):
        q = OfflineQueue()
        assert q.peek_pending("none") == []

    def test_filters_only_queued(self):
        q = OfflineQueue()
        q.enqueue(_op("a"))
        q.enqueue(_op("b"))
        q.mark_status("tnt_A", "a", SyncStatus.SYNCED)
        pending = q.peek_pending("tnt_A")
        assert [op.op_id for op in pending] == ["b"]

    def test_limit_truncates(self):
        q = OfflineQueue()
        for i in range(5):
            q.enqueue(_op(f"op{i}"))
        assert len(q.peek_pending("tnt_A", limit=2)) == 2

    def test_total_pending_counts_only_queued(self):
        q = OfflineQueue()
        q.enqueue(_op("a"))
        q.enqueue(_op("b"))
        q.mark_status("tnt_A", "a", SyncStatus.FAILED, error="e")
        # queue_size يعدّ الكلّ، total_pending يعدّ QUEUED فقط
        assert q.queue_size("tnt_A") == 2
        assert q.total_pending("tnt_A") == 1


# ─── enqueue: الحدّ الأقصى يُرجع False ────────────────────────────


class TestEnqueueLimit:
    def test_enqueue_returns_true_below_limit(self):
        q = OfflineQueue(max_per_tenant=2)
        assert q.enqueue(_op("a")) is True

    def test_enqueue_returns_false_at_limit(self):
        q = OfflineQueue(max_per_tenant=2)
        q.enqueue(_op("a"))
        q.enqueue(_op("b"))
        # الحدّ بلغ → الرفض صريح بـFalse
        assert q.enqueue(_op("c")) is False
        assert q.queue_size("tnt_A") == 2


# ─── clear_synced: retention للـaudit ────────────────────────────


class TestClearSynced:
    def test_unknown_tenant_returns_zero(self):
        q = OfflineQueue()
        assert q.clear_synced("none") == 0

    def test_old_synced_removed(self):
        q = OfflineQueue()
        op = _op("old", status=SyncStatus.SYNCED)
        op.synced_at = "2000-01-01T00:00:00"  # قديم جدّاً
        q.enqueue(op)
        removed = q.clear_synced("tnt_A", older_than_hours=24)
        assert removed == 1
        assert q.queue_size("tnt_A") == 0

    def test_recent_synced_kept(self):
        q = OfflineQueue()
        op = _op("recent", status=SyncStatus.SYNCED)
        op.synced_at = "2999-01-01T00:00:00"  # مستقبليّ → ليس متقادماً
        q.enqueue(op)
        removed = q.clear_synced("tnt_A", older_than_hours=24)
        assert removed == 0
        assert q.queue_size("tnt_A") == 1

    def test_non_synced_never_cleared(self):
        # QUEUED/FAILED تبقى مهما كان عمرها (لم تُنجز بعد)
        q = OfflineQueue()
        op = _op("queued", status=SyncStatus.QUEUED)
        op.synced_at = "2000-01-01T00:00:00"
        q.enqueue(op)
        assert q.clear_synced("tnt_A", older_than_hours=24) == 0
        assert q.queue_size("tnt_A") == 1


# ─── reset ───────────────────────────────────────────────────────


class TestReset:
    def test_reset_specific_tenant_only(self):
        q = OfflineQueue()
        q.enqueue(_op("a", tenant="tnt_A"))
        q.enqueue(_op("b", tenant="tnt_B"))
        q.reset("tnt_A")
        assert q.queue_size("tnt_A") == 0
        assert q.queue_size("tnt_B") == 1

    def test_reset_all(self):
        q = OfflineQueue()
        q.enqueue(_op("a", tenant="tnt_A"))
        q.enqueue(_op("b", tenant="tnt_B"))
        q.reset()
        assert q.queue_size("tnt_A") == 0
        assert q.queue_size("tnt_B") == 0


# ─── ConnectivityState ───────────────────────────────────────────


class TestConnectivityState:
    def test_defaults(self):
        s = ConnectivityState(is_online=True, last_check_at="2026-06-16T00:00:00")
        assert s.is_online is True
        assert s.consecutive_failures == 0
        assert s.reason_ar == ""

    def test_offline_with_failures(self):
        s = ConnectivityState(
            is_online=False,
            last_check_at="2026-06-16T00:00:00",
            consecutive_failures=3,
            reason_ar="انقطاع",
        )
        assert s.is_online is False
        assert s.consecutive_failures == 3


# ─── apply_supersession يُغيّر حالة الأقدم ─────────────────────────


class TestApplySupersessionEffect:
    def test_old_marked_superseded_new_stays_queued(self):
        q = OfflineQueue()
        q.enqueue(_op("old", payload={"field_id": "f1", "observable_id": "ndvi"}))
        q.enqueue(_op("new", payload={"field_id": "f1", "observable_id": "ndvi"}))
        count = apply_supersession(q, "tnt_A")
        assert count == 1
        by_id = {op.op_id: op for op in q._queues["tnt_A"]}
        assert by_id["old"].status == SyncStatus.SUPERSEDED
        assert by_id["new"].status == SyncStatus.QUEUED
        # سبب صريح يذكر العمليّة البديلة
        assert "new" in (by_id["old"].last_error or "")


# ─── SyncResult: رسائل reason_ar السلوكيّة ───────────────────────


class TestSyncResultMessaging:
    def _enqueue_n(self, q, n, tenant="tnt_A"):
        for i in range(n):
            record_operation_offline(
                q,
                tenant_id=tenant,
                user_id="u",
                kind=OperationKind.OBSERVATION_CREATE,
                payload={"field_id": f"f{i}"},
            )

    def test_empty_reason(self):
        q = OfflineQueue()
        res = sync_cycle(q, "tnt_A", sync_handler=lambda op: True)
        assert isinstance(res, SyncResult)
        assert "لا عمليّات معلّقة" in res.reason_ar
        assert res.duration_ms >= 0

    def test_all_synced_reason(self):
        q = OfflineQueue()
        self._enqueue_n(q, 2)
        res = sync_cycle(q, "tnt_A", sync_handler=lambda op: True)
        assert res.synced_count == 2
        assert "بنجاح" in res.reason_ar

    def test_conflict_reason_mentions_review(self):
        q = OfflineQueue()
        self._enqueue_n(q, 1)

        def handler(op):
            raise ValueError("duplicate key")

        res = sync_cycle(q, "tnt_A", sync_handler=handler)
        assert res.conflicted_count == 1
        assert "تضارب" in res.reason_ar

    def test_failure_reason_mentions_retry_later(self):
        q = OfflineQueue()
        self._enqueue_n(q, 1)

        def handler(op):
            raise ConnectionError("timeout")

        res = sync_cycle(q, "tnt_A", sync_handler=handler)
        assert res.failed_count == 1
        assert "سيُعاد لاحقاً" in res.reason_ar

    def test_max_batch_limits_processed(self):
        q = OfflineQueue()
        self._enqueue_n(q, 5)
        res = sync_cycle(q, "tnt_A", sync_handler=lambda op: True, max_batch=2)
        assert res.total_pending == 2
        assert res.synced_count == 2
        # الباقي ما زال معلّقاً
        assert q.total_pending("tnt_A") == 3

    def test_supersession_appended_to_reason(self):
        # عمليّتان على نفس الكيان: واحدة تُلغى، رسالة تذكر supersession
        q = OfflineQueue()
        record_operation_offline(
            q,
            tenant_id="tnt_A",
            user_id="u",
            kind=OperationKind.ACTIVITY_COMPLETE,
            payload={"field_id": "f1", "activity_id": "a1"},
        )
        record_operation_offline(
            q,
            tenant_id="tnt_A",
            user_id="u",
            kind=OperationKind.ACTIVITY_COMPLETE,
            payload={"field_id": "f1", "activity_id": "a1"},
        )
        res = sync_cycle(q, "tnt_A", sync_handler=lambda op: True)
        assert res.superseded_count == 1
        # الأحدث فقط syncت
        assert res.synced_count == 1
        assert "supersession" in res.reason_ar
