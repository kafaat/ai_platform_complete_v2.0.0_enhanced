"""Unit: تقوية محرّك السير/Saga (Stage A P1) — بلا قاعدة بيانات (DB-less).

يغطّي:
  ① مسار InMemory يبقى يعمل بلا DB (الافتراضيّ — CI أخضر).
  ② صدق fail-loud: فشل تعويض Saga يُسجَّل (ERROR) ويُدوَّن في الحالة
     (compensation_failures + status=COMPENSATION_FAILED) — لا ابتلاع صامت.
  ③ منطق الاختيار (Postgres vs InMemory) بحسب DATABASE_URL.
  ④ المخزن غير المتزامن (AsyncPostgresWorkflowStore) عبر اتّصال/تنفيذ مزيّف
     (fake conn) — save/load يُنتظران بـawait (لا asyncio.run).

كلّها منطق صرف بلا خدمات حيّة (marker unit).
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


def _wfe():
    """يحمّل core/workflow_engine.py كوحدة معزولة (بلا تبعيّات الخدمة)."""
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    spec = importlib.util.spec_from_file_location(
        "workflow_engine_hard",
        os.path.join(ROOT, "services/sahool-platform/core/workflow_engine.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["workflow_engine_hard"] = mod
    spec.loader.exec_module(mod)
    return mod


# ── ① InMemory يعمل بلا DB (الافتراضيّ) ────────────────────────────
@pytest.mark.unit
def test_inmemory_store_works_db_less():
    wfe = _wfe()
    store = wfe.InMemoryWorkflowStore()
    steps = [
        wfe.WorkflowStep("s1", lambda c: {"a": 1}),
        wfe.WorkflowStep("s2", lambda c: {"b": c["a"] + 1}),
    ]
    st = wfe.run_workflow("wf-inmem", steps, store=store, tenant_id="t1")
    assert st.status == wfe.WorkflowStatus.COMPLETED
    assert st.completed_steps == ["s1", "s2"]
    # الاستئناف من نفس المخزن لا يعيد التنفيذ (idempotent)
    loaded = store.load("wf-inmem")
    assert loaded is not None and loaded.context == {"a": 1, "b": 2}


@pytest.mark.unit
def test_inmemory_roundtrip_preserves_compensation_failures():
    # العمود الجديد يصمد عبر to_dict/from_dict (durability على مستوى التسلسل).
    wfe = _wfe()
    store = wfe.InMemoryWorkflowStore()
    st = wfe.WorkflowState(workflow_id="wf-rt", tenant_id="t1")
    st.compensation_failures.append({"step_id": "x", "error": "boom"})
    store.save(st)
    loaded = store.load("wf-rt")
    assert loaded.compensation_failures == [{"step_id": "x", "error": "boom"}]


# ── ② صدق fail-loud: فشل التعويض يُسجَّل ويُدوَّن ─────────────────────
@pytest.mark.unit
def test_compensation_failure_logs_and_marks_state(caplog):
    wfe = _wfe()
    store = wfe.InMemoryWorkflowStore()

    def comp_boom(ctx):
        raise RuntimeError("rollback exploded")

    steps = [
        wfe.WorkflowStep("s1", lambda c: {}, compensate=lambda c: None),
        wfe.WorkflowStep("s2", lambda c: {}, compensate=comp_boom),
        wfe.WorkflowStep("s3", lambda c: (_ for _ in ()).throw(RuntimeError("trigger"))),
    ]
    with caplog.at_level(logging.ERROR, logger="sahool.workflow_engine"):
        st = wfe.run_workflow(
            "wf-failloud", steps, store=store, tenant_id="t1", compensate_on_failure=True
        )

    # الحالة تُعلَن COMPENSATION_FAILED (لا COMPENSATED زائفة)
    assert st.status == wfe.WorkflowStatus.COMPENSATION_FAILED
    # دُوِّن الفشل في الحالة (يصمد + يظهر للرصد)
    assert [f["step_id"] for f in st.compensation_failures] == ["s2"]
    assert "rollback exploded" in st.compensation_failures[0]["error"]
    # s1 عُوِّضت بنجاح رغم فشل s2 (نُعوّض ما نستطيع)
    assert st.compensated_steps == ["s1"]
    # سُجِّل عند ERROR مع سياق كافٍ (workflow id + step)
    assert any(
        r.levelno == logging.ERROR and "wf-failloud" in r.getMessage() and "s2" in r.getMessage()
        for r in caplog.records
    ), "فشل التعويض لم يُسجَّل عند ERROR بسياق كافٍ"


@pytest.mark.unit
def test_successful_compensation_stays_compensated_not_failed():
    # لا فشل تعويض ⇒ COMPENSATED (لا compensation_failures) — ضدّ الإيجابيّة الكاذبة.
    wfe = _wfe()
    store = wfe.InMemoryWorkflowStore()
    steps = [
        wfe.WorkflowStep("s1", lambda c: {}, compensate=lambda c: None),
        wfe.WorkflowStep("s2", lambda c: (_ for _ in ()).throw(RuntimeError("x"))),
    ]
    st = wfe.run_workflow(
        "wf-okcomp", steps, store=store, tenant_id="t1", compensate_on_failure=True
    )
    assert st.status == wfe.WorkflowStatus.COMPENSATED
    assert st.compensation_failures == []


@pytest.mark.unit
def test_compensation_failed_is_terminal_and_needs_attention():
    wfe = _wfe()
    store = wfe.InMemoryWorkflowStore()

    body = {"s1": 0}

    def s1(ctx):
        body["s1"] += 1
        return {}

    steps = [
        wfe.WorkflowStep("s1", s1, compensate=lambda c: (_ for _ in ()).throw(RuntimeError("b"))),
        wfe.WorkflowStep("s2", lambda c: (_ for _ in ()).throw(RuntimeError("x"))),
    ]
    st1 = wfe.run_workflow(
        "wf-term", steps, store=store, tenant_id="t1", compensate_on_failure=True
    )
    assert st1.status == wfe.WorkflowStatus.COMPENSATION_FAILED
    # نهائيّة: إعادة التشغيل لا تُنفّذ خطوات ولا تُعيد المحاولة
    st2 = wfe.run_workflow(
        "wf-term", steps, store=store, tenant_id="t1", compensate_on_failure=True
    )
    assert st2.status == wfe.WorkflowStatus.COMPENSATION_FAILED
    assert body["s1"] == 1
    # الرصد يرفع علم الانتباه (نظام غير متّسق)
    tr = wfe.workflow_trace(st2)
    assert tr["needs_attention"] is True
    assert tr["compensation_failures"][0]["step_id"] == "s1"


# ── ③ منطق الاختيار (Postgres vs InMemory) بحسب DATABASE_URL ──────────
@pytest.mark.unit
def test_store_selection_inmemory_when_no_database_url(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-for-ci-only-0123456789")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as m
    from core.workflow_engine import InMemoryWorkflowStore

    m._INMEM_WORKFLOW_STORES.clear()
    store = m._get_workflow_store("tenant-X")
    assert isinstance(store, InMemoryWorkflowStore)


@pytest.mark.unit
def test_store_selection_postgres_when_database_url(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-for-ci-only-0123456789")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as m
    from core.workflow_engine import PostgresWorkflowStore

    # لا اتّصال فعليّ هنا — البناء فقط (asyncpg لا يُستدعى إلّا عند save/load)
    store = m._get_workflow_store("tenant-Y")
    assert isinstance(store, PostgresWorkflowStore)


# ── ④ المخزن غير المتزامن عبر اتّصال مزيّف (await، لا asyncio.run) ─────
class _FakeConn:
    """اتّصال asyncpg مزيّف: يخزّن آخر upsert ويُرجِعه عند fetchrow (روند-تريب)."""

    def __init__(self, store_dict: dict) -> None:
        self._d = store_dict

    async def execute(self, sql: str, *args):
        if "INSERT INTO workflow_state" in sql:
            # ترتيب الوسائط من _state_insert_args: workflow_id=args[0], compensation_failures=args[11]
            self._d[args[0]] = args
        return "OK"

    async def fetchrow(self, sql: str, workflow_id: str):
        import json

        args = self._d.get(workflow_id)
        if args is None:
            return None
        # يحاكي صفّ asyncpg: يدعم row["col"] و row.keys()
        return {
            "workflow_id": args[0],
            "tenant_id": args[1],
            "status": args[2],
            "completed_steps": json.loads(args[3]),
            "step_results": json.loads(args[4]),
            "context": json.loads(args[5]),
            "current_step": args[6],
            "error": args[7],
            "compensated_steps": json.loads(args[8]),
            "workflow_version": args[9],
            "correlation_id": args[10],
            "compensation_failures": json.loads(args[11]),
        }


class _FakePool:
    """pool مزيّف: acquire/release يُرجعان نفس الاتّصال المزيّف."""

    def __init__(self, conn) -> None:
        self._conn = conn

    async def acquire(self):
        return self._conn

    async def release(self, conn):
        return None


def _run(coro):
    import asyncio

    return asyncio.run(coro)


@pytest.mark.unit
def test_async_store_requires_dsn_or_pool():
    wfe = _wfe()
    with pytest.raises(ValueError):
        wfe.AsyncPostgresWorkflowStore()


@pytest.mark.unit
def test_async_store_save_requires_tenant():
    wfe = _wfe()
    conn = _FakeConn({})
    store = wfe.AsyncPostgresWorkflowStore(pool=_FakePool(conn))
    st = wfe.WorkflowState(workflow_id="wf-async", tenant_id=None)
    with pytest.raises(ValueError):
        _run(store.save(st))


@pytest.mark.unit
def test_async_store_save_load_roundtrip_via_await():
    wfe = _wfe()
    backing: dict = {}
    conn = _FakeConn(backing)
    store = wfe.AsyncPostgresWorkflowStore(pool=_FakePool(conn), tenant_id="t1")

    st = wfe.WorkflowState(workflow_id="wf-async", tenant_id="t1", context={"k": 1})
    st.completed_steps.append("s1")
    st.compensation_failures.append({"step_id": "s2", "error": "boom"})

    _run(store.save(st))
    loaded = _run(store.load("wf-async"))
    assert loaded is not None
    assert loaded.completed_steps == ["s1"]
    assert loaded.context == {"k": 1}
    # العمود الجديد يصمد عبر المخزن غير المتزامن
    assert loaded.compensation_failures == [{"step_id": "s2", "error": "boom"}]


@pytest.mark.unit
def test_async_store_load_missing_returns_none():
    wfe = _wfe()
    conn = _FakeConn({})
    store = wfe.AsyncPostgresWorkflowStore(pool=_FakePool(conn), tenant_id="t1")
    assert _run(store.load("nope")) is None


@pytest.mark.unit
def test_run_workflow_async_full_path_with_async_store():
    # المحرّك غير المتزامن يقود التدفّق عبر await store — لا asyncio.run داخليّاً.
    wfe = _wfe()
    conn = _FakeConn({})
    store = wfe.AsyncPostgresWorkflowStore(pool=_FakePool(conn), tenant_id="t1")
    calls: list[str] = []
    steps = [
        wfe.WorkflowStep("s1", lambda c: calls.append("s1") or {"a": 1}),
        wfe.WorkflowStep("s2", lambda c: calls.append("s2") or {"b": 2}),
    ]
    st = _run(wfe.run_workflow_async("wf-arun", steps, store=store, tenant_id="t1"))
    assert st.status == wfe.WorkflowStatus.COMPLETED
    assert calls == ["s1", "s2"]
    # «إعادة تشغيل»: تُحمَّل من القاعدة المزيّفة ولا تُعاد الخطوات
    st2 = _run(wfe.run_workflow_async("wf-arun", steps, store=store, tenant_id="t1"))
    assert st2.status == wfe.WorkflowStatus.COMPLETED
    assert calls == ["s1", "s2"]


@pytest.mark.unit
def test_run_workflow_async_compensation_failure_marks_state():
    # نظير الصدق fail-loud على المسار غير المتزامن.
    wfe = _wfe()
    conn = _FakeConn({})
    store = wfe.AsyncPostgresWorkflowStore(pool=_FakePool(conn), tenant_id="t1")

    def comp_boom(ctx):
        raise RuntimeError("async rollback failed")

    steps = [
        wfe.WorkflowStep("s1", lambda c: {}, compensate=lambda c: None),
        wfe.WorkflowStep("s2", lambda c: {}, compensate=comp_boom),
        wfe.WorkflowStep("s3", lambda c: (_ for _ in ()).throw(RuntimeError("x"))),
    ]
    st = _run(
        wfe.run_workflow_async(
            "wf-acomp", steps, store=store, tenant_id="t1", compensate_on_failure=True
        )
    )
    assert st.status == wfe.WorkflowStatus.COMPENSATION_FAILED
    assert [f["step_id"] for f in st.compensation_failures] == ["s2"]
    assert st.compensated_steps == ["s1"]
