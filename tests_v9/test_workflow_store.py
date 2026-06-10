"""Integration test: PostgresWorkflowStore durability (resume across restart).

يُثبت أنّ الحالة تصمد عبر «إعادة تشغيل» (نسخة store جديدة) فلا يُعاد تنفيذ
الخطوات المكتملة — جوهر الحفظ المعمّر الذي لا يوفّره InMemory.

pytest -m integration (يتخطّى تلقائيّاً إن لم تتوفّر القاعدة).
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
        "workflow_engine", os.path.join(ROOT, "services/sahool-platform/core/workflow_engine.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["workflow_engine"] = mod
    spec.loader.exec_module(mod)
    return mod


def _db_available() -> bool:
    try:
        import asyncio

        import asyncpg

        async def _ping():
            c = await asyncpg.connect(DSN)
            await c.execute("SELECT 1 FROM workflow_state LIMIT 0")  # v16/v17 applied?
            await c.close()

        asyncio.run(_ping())
        return True
    except Exception:
        return False


@pytest.mark.integration
def test_postgres_store_durable_resume():
    if not _db_available():
        pytest.skip("DATABASE_URL/workflow_state غير متاح — اختبار تكامل")
    wfe = _wfe()
    calls: list = []
    steps = [
        wfe.WorkflowStep("s1", lambda c: calls.append("s1") or {"a": 1}),
        wfe.WorkflowStep("s2", lambda c: calls.append("s2") or {"b": 2}),
    ]
    wid = f"wf-itest-{os.getpid()}"
    store1 = wfe.PostgresWorkflowStore(DSN)
    try:
        st = wfe.run_workflow(wid, steps, store=store1, tenant_id=_TENANT)
        assert st.status.value == "completed" and calls == ["s1", "s2"]

        # «إعادة تشغيل»: نسخة store جديدة (الذاكرة فُقدت) — تُحمّل من القاعدة.
        # تمرير tenant_id ضروريّ: workflow_state عليه RLS+FORCE، فبدون ضبط
        # app.current_tenant تحجب السياسة الصفوف (load=None).
        store2 = wfe.PostgresWorkflowStore(DSN, tenant_id=_TENANT)
        loaded = store2.load(wid)
        assert loaded is not None and loaded.completed_steps == ["s1", "s2"]
        assert loaded.context == {"a": 1, "b": 2}  # السياق المتراكم صمد

        # الاستئناف لا يعيد تنفيذ المكتمل
        wfe.run_workflow(wid, steps, store=store2, tenant_id=_TENANT)
        assert calls == ["s1", "s2"], f"steps re-ran across restart: {calls}"
    finally:
        import asyncio

        import asyncpg

        async def _clean():
            c = await asyncpg.connect(DSN)
            await c.execute("DELETE FROM workflow_state WHERE workflow_id=$1", wid)
            await c.close()

        asyncio.run(_clean())
