"""اختبار تكامل: ربط offline-sync و HIL get_status بكتابة/قراءة DB فعليّة.

يغطّي إصلاحين كانا placeholders:
  • services/sahool-platform/api/offline_sync_db.persist_synced_operation /
    fetch_synced_operations — كتابة عمليّات offline المُزامَنة بمتانة، idempotent
    على op_id، مع عزل RLS (يُختبَر عبر دور غير ممتاز يُطبَّق عليه RLS فعلاً).
  • services/guardrails-engine/human_in_loop.HumanApprovalWorkflow.get_status —
    استعلام DB حقيقي بدل None الثابتة.

يعمل عبر: pytest -m integration (يتخطّى تلقائيّاً إن لم تتوفّر قاعدة البيانات).
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test",
)
RLS_ROLE = "sahool_rls_test"  # دور غير ممتاز ليُطبَّق RLS فعلاً (المالك/السوبر يتجاوزه)


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


async def _connect():
    import asyncpg

    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


@pytest.fixture
async def db():
    try:
        conn = await _connect()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"قاعدة البيانات غير متاحة: {type(e).__name__}")
    yield conn
    await conn.close()


@pytest.mark.integration
class TestOfflineSyncPersistence:
    """persist/fetch لعمليّات offline-first مع idempotency وعزل RLS."""

    async def _make_op(self, mod_core, tenant_id: str, user_id: str = "tester"):
        return mod_core.PendingOperation(
            op_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            kind=mod_core.OperationKind.OBSERVATION_CREATE,
            payload={"field_id": "f-001", "note": "ملاحظة حقل"},
            created_at="2026-06-10T08:00:00",
            user_id=user_id,
        )

    async def test_persist_idempotent_and_isolated(self, db):
        # حمّل النواة النقيّة + طبقة الكتابة
        if os.path.join(ROOT, "services/sahool-platform") not in sys.path:
            sys.path.insert(0, os.path.join(ROOT, "services/sahool-platform"))
        core = _load("services/sahool-platform/core/offline_first.py", "core.offline_first")
        osd = _load("services/sahool-platform/api/offline_sync_db.py", "offline_sync_db")

        # تهيئة دور غير ممتاز يُطبَّق عليه RLS (المالك يتجاوز FORCE وحده لا السوبر)
        await db.execute(f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{RLS_ROLE}') THEN
                    CREATE ROLE {RLS_ROLE} NOSUPERUSER NOBYPASSRLS;
                END IF;
            END $$;
        """)
        await db.execute(f"GRANT USAGE ON SCHEMA public TO {RLS_ROLE}")
        await db.execute(
            f"GRANT SELECT, INSERT ON offline_synced_operations TO {RLS_ROLE}"
        )

        tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
        op = await self._make_op(core, tenant_a)

        try:
            # كمستأجر A عبر الدور غير الممتاز (RLS فعّال)
            await db.execute(f"SET ROLE {RLS_ROLE}")
            await db.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)

            assert await osd.persist_synced_operation(db, op=op, tenant_id=tenant_a) is True
            ids = [r["op_id"] for r in await osd.fetch_synced_operations(db)]
            assert op.op_id in ids, "العمليّة لم تُكتب/تُقرأ للمستأجر A"

            # idempotency: إعادة الـsync بنفس op_id لا تُكرّر الصفّ
            await osd.persist_synced_operation(db, op=op, tenant_id=tenant_a)
            ids2 = [r["op_id"] for r in await osd.fetch_synced_operations(db)]
            assert ids2.count(op.op_id) == 1, "ON CONFLICT لم يمنع التكرار"

            # عزل: المستأجر B لا يرى عمليّة A
            await db.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_b)
            ids_b = [r["op_id"] for r in await osd.fetch_synced_operations(db)]
            assert op.op_id not in ids_b, "🚨 تسرّب: B يرى عمليّة A (RLS مكسور)"
        finally:
            await db.execute("RESET ROLE")
            await db.execute("DELETE FROM offline_synced_operations WHERE op_id=$1", op.op_id)


@pytest.mark.integration
class TestHILGetStatus:
    """get_status يقرأ workflow حقيقيّاً من القاعدة (كان يُرجع None دائماً)."""

    async def test_create_then_get_status(self, db):
        os.environ["DATABASE_URL"] = DATABASE_URL
        sys.path.insert(0, os.path.join(ROOT, "services/guardrails-engine"))
        hil_mod = _load("services/guardrails-engine/human_in_loop.py", "human_in_loop_test")
        hil = hil_mod.HumanApprovalWorkflow()

        req = types.SimpleNamespace(
            tenant_id=str(uuid.uuid4()),
            user_id=42,  # approval_workflows.user_id عمود INTEGER
            action_type="pesticide_application",
            action_data={"product": "X", "rate": 1.5},
            farm_context={"field_id": "f-001"},
        )
        checks = [{"passed": False, "tier": "chemical"}]

        wf_id = None
        try:
            wf_id = await hil.create(req, checks, "HIGH")
            status = await hil.get_status(wf_id)
            assert status is not None, "get_status أرجع None لـworkflow موجود (placeholder لم يُصلَح)"
            assert status["workflow_id"] == wf_id
            assert status["status"] == "pending"
            assert status["risk_level"] == "HIGH"
            assert isinstance(status["required_roles"], list) and status["required_roles"]

            # workflow غير موجود ⇒ None
            assert await hil.get_status("SAHOOL-HIL-NOPE0000") is None
        finally:
            if wf_id:
                await db.execute("DELETE FROM approval_workflows WHERE workflow_id=$1", wf_id)
