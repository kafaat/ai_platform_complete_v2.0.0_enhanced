"""Tests for offline_first - explicit offline-first architecture.
Resolves the philosophical gap from AI Ag Template: 'offline as default'."""
from datetime import datetime, timedelta
from core.offline_first import (
    OfflineQueue, PendingOperation, OperationKind, SyncStatus,
    record_operation_offline, sync_cycle, queue_summary,
    detect_superseded, apply_supersession, SyncResult,
    ConnectivityState)


def _make_obs_op(tenant="tnt_001", field="fld_01", value=0.5):
    """Helper: create observation operation."""
    import uuid
    return PendingOperation(
        op_id=str(uuid.uuid4()),
        tenant_id=tenant, user_id="u1",
        kind=OperationKind.OBSERVATION_CREATE,
        payload={"field_id": field, "observable_id": "ndvi",
                "value": value, "measured_at": "2026-05-29T00:00:00"},
        created_at=datetime.utcnow().isoformat(),
    )


class TestQueueBasics:
    def test_empty_queue_zero_size(self):
        q = OfflineQueue()
        assert q.queue_size("tnt_001") == 0
        assert q.total_pending("tnt_001") == 0

    def test_enqueue_increases_size(self):
        q = OfflineQueue()
        q.enqueue(_make_obs_op())
        assert q.queue_size("tnt_001") == 1

    def test_max_per_tenant_enforced(self):
        # CRITICAL: لا overflow بدون قيود
        q = OfflineQueue(max_per_tenant=3)
        for i in range(5):
            q.enqueue(_make_obs_op(field=f"fld_{i}"))
        # يحفظ آخر 3 (deque maxlen)
        assert q.queue_size("tnt_001") == 3


class TestTenantIsolation:
    """الخطّ الأحمر — لا تسريب بين tenants."""

    def test_separate_queues(self):
        # CRITICAL: tnt_001 وtnt_002 منفصلان كلياً
        q = OfflineQueue()
        q.enqueue(_make_obs_op(tenant="tnt_001"))
        q.enqueue(_make_obs_op(tenant="tnt_002"))
        q.enqueue(_make_obs_op(tenant="tnt_002"))

        assert q.queue_size("tnt_001") == 1
        assert q.queue_size("tnt_002") == 2

    def test_peek_only_own_tenant(self):
        # CRITICAL: peek لا يكشف tenant آخر
        q = OfflineQueue()
        q.enqueue(_make_obs_op(tenant="tnt_001"))
        q.enqueue(_make_obs_op(tenant="tnt_002"))

        pending_001 = q.peek_pending("tnt_001")
        assert all(op.tenant_id == "tnt_001" for op in pending_001)

    def test_mark_status_per_tenant(self):
        # mark_status على tnt_001 لا يلمس tnt_002
        q = OfflineQueue()
        op1 = _make_obs_op(tenant="tnt_001")
        op2 = _make_obs_op(tenant="tnt_002")
        q.enqueue(op1)
        q.enqueue(op2)
        q.mark_status("tnt_001", op1.op_id, SyncStatus.SYNCED)

        # op2 لا يزال QUEUED
        pending_002 = q.peek_pending("tnt_002")
        assert all(op.status == SyncStatus.QUEUED for op in pending_002)


class TestRecordOperation:
    def test_record_creates_uuid(self):
        # CRITICAL: كل عملية تحصل على UUID فريد
        q = OfflineQueue()
        op1 = record_operation_offline(
            q, tenant_id="tnt_001", user_id="u",
            kind=OperationKind.OBSERVATION_CREATE,
            payload={"field_id": "f1"})
        op2 = record_operation_offline(
            q, tenant_id="tnt_001", user_id="u",
            kind=OperationKind.OBSERVATION_CREATE,
            payload={"field_id": "f1"})
        assert op1.op_id != op2.op_id

    def test_record_sets_created_at(self):
        q = OfflineQueue()
        op = record_operation_offline(
            q, tenant_id="tnt_001", user_id="u",
            kind=OperationKind.ACTIVITY_COMPLETE,
            payload={"activity_id": "a1"})
        assert op.created_at
        # تاريخ صالح
        datetime.fromisoformat(op.created_at.replace("Z", ""))


class TestSupersession:
    """عمليات لاحقة تُلغي السابقة على نفس الكيان."""

    def test_two_completes_same_activity(self):
        # CRITICAL: نفس activity_id مرّتين → الأقدم superseded
        q = OfflineQueue()
        record_operation_offline(
            q, tenant_id="tnt_001", user_id="u",
            kind=OperationKind.ACTIVITY_COMPLETE,
            payload={"activity_id": "act_X", "field_id": "f1"})
        record_operation_offline(
            q, tenant_id="tnt_001", user_id="u",
            kind=OperationKind.ACTIVITY_COMPLETE,
            payload={"activity_id": "act_X", "field_id": "f1"})

        count = apply_supersession(q, "tnt_001")
        assert count == 1

    def test_different_activities_not_superseded(self):
        q = OfflineQueue()
        record_operation_offline(
            q, tenant_id="tnt_001", user_id="u",
            kind=OperationKind.ACTIVITY_COMPLETE,
            payload={"activity_id": "act_A", "field_id": "f1"})
        record_operation_offline(
            q, tenant_id="tnt_001", user_id="u",
            kind=OperationKind.ACTIVITY_COMPLETE,
            payload={"activity_id": "act_B", "field_id": "f1"})

        count = apply_supersession(q, "tnt_001")
        assert count == 0   # نشاطان مختلفان

    def test_no_supersession_across_tenants(self):
        # CRITICAL: نفس activity_id في tnt مختلفَين → لا supersession
        q = OfflineQueue()
        record_operation_offline(
            q, tenant_id="tnt_001", user_id="u",
            kind=OperationKind.ACTIVITY_COMPLETE,
            payload={"activity_id": "act_X", "field_id": "f1"})
        record_operation_offline(
            q, tenant_id="tnt_002", user_id="u",
            kind=OperationKind.ACTIVITY_COMPLETE,
            payload={"activity_id": "act_X", "field_id": "f1"})

        count_001 = apply_supersession(q, "tnt_001")
        count_002 = apply_supersession(q, "tnt_002")
        # كلّ tenant عنده عملية واحدة فقط، لا supersession
        assert count_001 == 0
        assert count_002 == 0


class TestSyncCycle:
    """دورة sync — يجب أن تكون pure (NO actual network)."""

    def test_empty_queue_no_error(self):
        q = OfflineQueue()
        result = sync_cycle(q, "tnt_empty", sync_handler=lambda op: True)
        assert result.total_pending == 0
        assert result.synced_count == 0

    def test_all_success(self):
        q = OfflineQueue()
        for i in range(3):
            record_operation_offline(
                q, tenant_id="tnt_001", user_id="u",
                kind=OperationKind.OBSERVATION_CREATE,
                payload={"field_id": f"f_{i}", "value": 0.5})

        result = sync_cycle(q, "tnt_001", sync_handler=lambda op: True)
        assert result.synced_count == 3
        assert result.failed_count == 0

    def test_failures_kept_in_queue(self):
        # CRITICAL: فشل sync لا يُسقط العملية — تبقى للمحاولة لاحقاً
        q = OfflineQueue()
        record_operation_offline(
            q, tenant_id="tnt_001", user_id="u",
            kind=OperationKind.OBSERVATION_CREATE,
            payload={"field_id": "f1"})

        def failing(op):
            raise ConnectionError("network down")

        result = sync_cycle(q, "tnt_001", sync_handler=failing)
        assert result.failed_count == 1
        # العملية ما زالت في الـqueue (بحالة FAILED، لا QUEUED)
        assert q.queue_size("tnt_001") == 1

    def test_conflict_detected_vs_failure(self):
        # CRITICAL: "conflict" يُصنّف منفصلاً عن "failure"
        q = OfflineQueue()
        record_operation_offline(
            q, tenant_id="tnt_001", user_id="u",
            kind=OperationKind.OBSERVATION_CREATE,
            payload={"field_id": "f1"})

        def conflict_handler(op):
            raise ValueError("CONFLICT: duplicate")

        result = sync_cycle(q, "tnt_001", sync_handler=conflict_handler)
        assert result.conflicted_count == 1
        assert result.failed_count == 0

    def test_handler_returning_false_counts_failure(self):
        q = OfflineQueue()
        record_operation_offline(
            q, tenant_id="tnt_001", user_id="u",
            kind=OperationKind.OBSERVATION_CREATE,
            payload={"field_id": "f1"})

        result = sync_cycle(q, "tnt_001", sync_handler=lambda op: False)
        assert result.failed_count == 1


class TestRetryBehavior:
    """عمليات فاشلة قابلة لإعادة المحاولة."""

    def test_retry_count_increments(self):
        q = OfflineQueue()
        record_operation_offline(
            q, tenant_id="tnt_001", user_id="u",
            kind=OperationKind.OBSERVATION_CREATE,
            payload={"field_id": "f1"})

        def fail(op):
            raise ConnectionError("temporary")

        sync_cycle(q, "tnt_001", sync_handler=fail)
        # العملية الآن FAILED، retry_count=1
        all_ops = list(q._queues["tnt_001"])
        assert all_ops[0].retry_count == 1


class TestQueueSummary:
    def test_summary_shows_breakdown(self):
        q = OfflineQueue()
        record_operation_offline(
            q, tenant_id="tnt_001", user_id="u",
            kind=OperationKind.OBSERVATION_CREATE,
            payload={"field_id": "f1"})

        summary = queue_summary(q, "tnt_001")
        assert summary["total_in_queue"] == 1
        assert "queued" in summary["by_status"]

    def test_summary_empty_tenant(self):
        # CRITICAL: لا اختراع — tenant فارغ يُرجع 0 صريح
        q = OfflineQueue()
        summary = queue_summary(q, "tnt_empty")
        assert summary["total_in_queue"] == 0


class TestNoNetworkInTests:
    """ضمان: لا اختبار يحتاج network فعلاً (الإثبات التجريبي لـoffline-first)."""

    def test_pure_python_only(self):
        # كل sync_handler هو callable من المستدعي
        # النواة لا تستورد requests, urllib, httpx
        import core.offline_first as off
        import inspect
        src = inspect.getsource(off)
        forbidden = ["import requests", "import urllib", "import httpx",
                    "import aiohttp", "urlopen("]
        for bad in forbidden:
            assert bad not in src, f"offline_first يستورد {bad}!"
