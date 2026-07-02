"""v19.5-1: عقد الكاتب-الواحد على workflow_state (single-writer lease).

يُثبت أنّ حارس العقد (v135) يمنع عاملَين من استئناف نفس workflow_id معاً
(تنفيذ مزدوج لأثر جانبيّ)، مع بقاء مسار الاستئناف المعمّر بلا تغيير:

  (unit)        منطق الرفض النقيّ _lease_refuses (DB-less — أخضر في CI بلا قاعدة).
  (integration) ① عاملان يطالبان بنفس الـworkflow ⇒ واحد فقط ينفّذ، الآخر يُرفض.
                ② عقد منتهٍ قابل لإعادة المطالبة من عامل جديد.
                ③ الإكمال يحرّر العقد + الاستئناف لا يعيد تنفيذ المكتمل (durable).

pytest -m integration (يتخطّى تلقائيّاً إن لم تتوفّر القاعدة/الهجرة v135).
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
_TENANT = "11111111-1111-1111-1111-111111111111"


def _wfe():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    spec = importlib.util.spec_from_file_location(
        "workflow_engine_lease",
        os.path.join(ROOT, "services/sahool-platform/core/workflow_engine.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["workflow_engine_lease"] = mod
    spec.loader.exec_module(mod)
    return mod


# ── unit: منطق الرفض النقيّ (بلا قاعدة) ──────────────────────────────
@pytest.mark.unit
def test_lease_refuses_pure_helper():
    wfe = _wfe()
    # عقد حيّ بيد مالك مختلف ⇒ رفض (يمنع التنفيذ المزدوج)
    assert wfe._lease_refuses("worker-A", True, "worker-B") is True
    # نفس المالك ⇒ لا رفض (تجديد مشروع)
    assert wfe._lease_refuses("worker-A", True, "worker-A") is False
    # عقد غير حيّ (منتهٍ) ⇒ لا رفض (قابل لإعادة المطالبة)
    assert wfe._lease_refuses("worker-A", False, "worker-B") is False
    # لا مالك ⇒ لا رفض (عقد فارغ)
    assert wfe._lease_refuses(None, False, "worker-B") is False


# ── أدوات تكامل (قاعدة حيّة) ─────────────────────────────────────────
def _db_available() -> bool:
    try:
        import asyncio

        import asyncpg

        async def _ping():
            c = await asyncpg.connect(DSN)
            # v135 مُطبَّقة؟ (عمود العقد موجود)
            await c.execute("SELECT lease_owner, lease_expires_at FROM workflow_state LIMIT 0")
            await c.close()

        asyncio.run(_ping())
        return True
    except Exception:
        return False


def _exec(sql: str, *args) -> None:
    """ينفّذ SQL بسياق مستأجر _TENANT (لتجاوز RLS في الإعداد/التنظيف)."""
    import asyncio

    import asyncpg

    async def _run():
        c = await asyncpg.connect(DSN)
        try:
            await c.execute("SELECT set_config('app.current_tenant', $1, false)", _TENANT)
            await c.execute(sql, *args)
        finally:
            await c.close()

    asyncio.run(_run())


def _cleanup(wid: str) -> None:
    _exec("DELETE FROM workflow_state WHERE workflow_id=$1", wid)


# ── ① عاملان: واحد فقط ينفّذ، الآخر يُرفض ────────────────────────────
@pytest.mark.integration
def test_two_workers_single_writer_refusal():
    if not _db_available():
        pytest.skip("workflow_state/v135 غير متاح — اختبار تكامل")
    wfe = _wfe()
    wid = f"wf-lease-refuse-{os.getpid()}"
    a = wfe.PostgresWorkflowStore(DSN, tenant_id=_TENANT, worker_id="worker-A", lease_seconds=300)
    b = wfe.PostgresWorkflowStore(DSN, tenant_id=_TENANT, worker_id="worker-B", lease_seconds=300)
    try:
        # A يستأنف الآن: حالة RUNNING ⇒ عقد حيّ باسم worker-A.
        st = wfe.WorkflowState(
            workflow_id=wid, tenant_id=_TENANT, status=wfe.WorkflowStatus.RUNNING
        )
        a.save(st)
        # A يطالب (يجدّد) بنجاح — نفس المالك
        assert a.claim(wid) is not None
        # B يُرفض: عقد حيّ لعامل آخر
        with pytest.raises(wfe.WorkflowLeasedError):
            b.claim(wid)
        # وعبر run_workflow: B لا ينفّذ أيّ خطوة (لا تنفيذ مزدوج)
        calls: list[str] = []
        steps = [wfe.WorkflowStep("s1", lambda c: calls.append("s1") or {})]
        with pytest.raises(wfe.WorkflowLeasedError):
            wfe.run_workflow(wid, steps, store=b, tenant_id=_TENANT)
        assert calls == [], "B نفّذ خطوة رغم العقد الحيّ لـA (تنفيذ مزدوج)"
    finally:
        _cleanup(wid)


# ── ② عقد منتهٍ قابل لإعادة المطالبة ─────────────────────────────────
@pytest.mark.integration
def test_expired_lease_reclaimable_by_new_owner():
    if not _db_available():
        pytest.skip("workflow_state/v135 غير متاح — اختبار تكامل")
    wfe = _wfe()
    wid = f"wf-lease-expire-{os.getpid()}"
    a = wfe.PostgresWorkflowStore(DSN, tenant_id=_TENANT, worker_id="worker-A", lease_seconds=300)
    b = wfe.PostgresWorkflowStore(DSN, tenant_id=_TENANT, worker_id="worker-B", lease_seconds=300)
    try:
        st = wfe.WorkflowState(
            workflow_id=wid, tenant_id=_TENANT, status=wfe.WorkflowStatus.RUNNING
        )
        a.save(st)  # A يحجز عقداً حيّاً
        # محاكاة انتهاء العقد (العامل A تعطّل): ندفع lease_expires_at إلى الماضي.
        _exec(
            "UPDATE workflow_state SET lease_expires_at = NOW() - interval '1 hour' "
            "WHERE workflow_id=$1",
            wid,
        )
        # B يُعيد المطالبة بنجاح (العقد منتهٍ ⇒ قابل للاستيلاء)
        reclaimed = b.claim(wid)
        assert reclaimed is not None
        # الآن A يُرفض: B يملك عقداً حيّاً
        with pytest.raises(wfe.WorkflowLeasedError):
            a.claim(wid)
    finally:
        _cleanup(wid)


# ── ③ الإكمال يحرّر العقد + الاستئناف لا يعيد تنفيذ المكتمل ───────────
@pytest.mark.integration
def test_completion_releases_lease_and_resume_not_rerun():
    if not _db_available():
        pytest.skip("workflow_state/v135 غير متاح — اختبار تكامل")
    wfe = _wfe()
    wid = f"wf-lease-resume-{os.getpid()}"
    calls: list[str] = []
    steps = [
        wfe.WorkflowStep("s1", lambda c: calls.append("s1") or {"a": 1}),
        wfe.WorkflowStep("s2", lambda c: calls.append("s2") or {"b": 2}),
    ]
    a = wfe.PostgresWorkflowStore(DSN, tenant_id=_TENANT, worker_id="worker-A")
    try:
        st = wfe.run_workflow(wid, steps, store=a, tenant_id=_TENANT)
        assert st.status.value == "completed" and calls == ["s1", "s2"]
        # العقد حُرِّر عند الإكمال ⇒ عامل آخر لا يُرفض (workflow خامل نهائيّ).
        b = wfe.PostgresWorkflowStore(DSN, tenant_id=_TENANT, worker_id="worker-B")
        loaded = b.claim(wid)  # لا WorkflowLeasedError (العقد محرَّر)
        assert loaded is not None and loaded.completed_steps == ["s1", "s2"]
        assert loaded.context == {"a": 1, "b": 2}
        # الاستئناف عبر عامل ثانٍ لا يعيد تنفيذ المكتمل (durable resume صامد)
        st2 = wfe.run_workflow(wid, steps, store=b, tenant_id=_TENANT)
        assert st2.status.value == "completed"
        assert calls == ["s1", "s2"], f"أُعيد تنفيذ خطوات عبر الاستئناف: {calls}"
    finally:
        _cleanup(wid)


# ── (v19.5-2) المخزن غير المتزامن: نفس حارس الكاتب-الواحد على المسار async-native ─
# قبل هذا السلايس كان AsyncPostgresWorkflowStore بلا claim فيسقط لـload (لا عقد) —
# عاملان async يستأنفان نفس workflow_id فينفّذان الخطوات معاً. هنا نُثبت أنّ إضافة
# claim غير المتزامن تغلق الفجوة: عامل واحد ينفّذ، الآخر يُرفض؛ والعقد المنتهي قابل
# لإعادة المطالبة. asyncpg بـstatement_cache_size=0 (متوافق مع pgbouncer/الاختبار).
def _apool():
    """pool غير متزامن (statement_cache_size=0) — يُنشأ داخل حلقة الاختبار."""
    import asyncpg

    return asyncpg.create_pool(DSN, statement_cache_size=0)


@pytest.mark.integration
def test_async_two_workers_single_writer_refusal():
    if not _db_available():
        pytest.skip("workflow_state/v135 غير متاح — اختبار تكامل")
    wfe = _wfe()
    wid = f"wf-alease-refuse-{os.getpid()}"

    async def _scenario():
        pool = await _apool()
        try:
            a = wfe.AsyncPostgresWorkflowStore(
                pool=pool, tenant_id=_TENANT, worker_id="aw-A", lease_seconds=300
            )
            b = wfe.AsyncPostgresWorkflowStore(
                pool=pool, tenant_id=_TENANT, worker_id="aw-B", lease_seconds=300
            )
            # A يستأنف الآن: RUNNING ⇒ عقد حيّ باسم aw-A.
            st = wfe.WorkflowState(
                workflow_id=wid, tenant_id=_TENANT, status=wfe.WorkflowStatus.RUNNING
            )
            await a.save(st)
            # A يطالب (يجدّد) بنجاح — نفس المالك.
            assert await a.claim(wid) is not None
            # B يُرفض: عقد حيّ لعامل آخر.
            with pytest.raises(wfe.WorkflowLeasedError):
                await b.claim(wid)
            # وعبر run_workflow_async: B لا ينفّذ أيّ خطوة (لا تنفيذ مزدوج) ولا يُعطّل.
            calls: list[str] = []
            steps = [wfe.WorkflowStep("s1", lambda c: calls.append("s1") or {})]
            with pytest.raises(wfe.WorkflowLeasedError):
                await wfe.run_workflow_async(wid, steps, store=b, tenant_id=_TENANT)
            assert calls == [], "B نفّذ خطوة رغم العقد الحيّ لـA (تنفيذ مزدوج)"
        finally:
            await pool.close()

    import asyncio

    try:
        asyncio.run(_scenario())
    finally:
        _cleanup(wid)


@pytest.mark.integration
def test_async_expired_lease_reclaimable_by_new_owner():
    if not _db_available():
        pytest.skip("workflow_state/v135 غير متاح — اختبار تكامل")
    wfe = _wfe()
    wid = f"wf-alease-expire-{os.getpid()}"

    async def _scenario():
        pool = await _apool()
        try:
            a = wfe.AsyncPostgresWorkflowStore(
                pool=pool, tenant_id=_TENANT, worker_id="aw-A", lease_seconds=300
            )
            b = wfe.AsyncPostgresWorkflowStore(
                pool=pool, tenant_id=_TENANT, worker_id="aw-B", lease_seconds=300
            )
            st = wfe.WorkflowState(
                workflow_id=wid, tenant_id=_TENANT, status=wfe.WorkflowStatus.RUNNING
            )
            await a.save(st)  # A يحجز عقداً حيّاً
            # محاكاة انتهاء العقد (العامل A تعطّل): ندفع lease_expires_at إلى الماضي.
            async with pool.acquire() as c:
                await c.execute("SELECT set_config('app.current_tenant', $1, false)", _TENANT)
                await c.execute(
                    "UPDATE workflow_state SET lease_expires_at = NOW() - interval '1 hour' "
                    "WHERE workflow_id=$1",
                    wid,
                )
            # B يُعيد المطالبة بنجاح (العقد منتهٍ ⇒ قابل للاستيلاء).
            reclaimed = await b.claim(wid)
            assert reclaimed is not None
            # الآن A يُرفض: B يملك عقداً حيّاً.
            with pytest.raises(wfe.WorkflowLeasedError):
                await a.claim(wid)
        finally:
            await pool.close()

    import asyncio

    try:
        asyncio.run(_scenario())
    finally:
        _cleanup(wid)
