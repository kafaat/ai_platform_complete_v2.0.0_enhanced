"""F-D11 — a recorded input deducts from a named inventory batch only behind its flag (live PG).

The farm ledger summed input quantities and never moved stock. The platform owns
``inventory_batches`` (``docs/architecture/db_ownership.yml``), so the deduction is a step of
``POST /api/v1/farm-ledger/operations`` itself: an input naming ``inventory_batch_id`` locks that
batch row, refuses on another tenant's batch, a different item or unit, or insufficient stock,
and deducts in the same transaction as the ledger record, under the ``Idempotency-Key``
receipt. ``FEATURE_LEDGER_INVENTORY_DEDUCTION`` is OFF by default; with it off nothing moves.

The router runs against the migrated schema through a pool that runs as a NOBYPASSRLS role,
so tenant isolation applies as in production. No stand-in connection.

Env: ``TEST_DATABASE_URL`` (owner DSN; a NOBYPASSRLS role is made for the pool when it is a
superuser). ``FARM_LEDGER_INVENTORY_CERTIFICATION_REQUIRED=1`` turns every skip into a failure.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

import pytest

CERTIFICATION_REQUIRED = os.getenv("FARM_LEDGER_INVENTORY_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
except ImportError:
    if CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg", reason="asyncpg not installed")
pytest.importorskip("fastapi")

pytestmark = [pytest.mark.integration]

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
# The module connects as the schema owner and creates its own throwaway NOBYPASSRLS role for the
# request path. On its certifying CI step the owner comes from TEST_DATABASE_ADMIN_URL, so the
# step's TEST_DATABASE_URL never names a privileged role.
DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
TABLES = (
    "farms",
    "farm_operation_ledger",
    "farm_input_records",
    "inventory_items",
    "inventory_batches",
    "commands",
)
FLAG = "FEATURE_LEDGER_INVENTORY_DEDUCTION"


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in TABLES:
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
if _WHY and CERTIFICATION_REQUIRED:
    raise RuntimeError(f"FARM_LEDGER_INVENTORY_CERTIFICATION_REQUIRED=1 but {_WHY}")
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main
    from api.routers import farm_operations_ledger

    return main, farm_operations_ledger


def _user(tenant: str):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id=f"u-{uuid.uuid4().hex[:8]}", tenant_id=tenant, role=UserRole.OWNER, name_ar="مالك"
    )


class Live:
    """Owner connection for seeding + a pool that runs as a NOBYPASSRLS role."""

    def __init__(self):
        self.tenant = str(uuid.uuid4())
        self.other_tenant = str(uuid.uuid4())
        tag = uuid.uuid4().hex[:10]
        self.farm_id = f"inv-farm-{tag}"
        self.item_id = f"inv-item-{tag}"
        self.batch_id = f"inv-batch-{tag}"
        self.foreign_item = f"inv-fitem-{tag}"
        self.foreign_batch = f"inv-fbatch-{tag}"
        self.role: str | None = None

    async def __aenter__(self):
        self.owner = await asyncpg.connect(DSN)
        if await self.owner.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ):
            self.role = f"inv_rls_{uuid.uuid4().hex[:10]}"
            await self.owner.execute(
                f'CREATE ROLE "{self.role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
                f'GRANT USAGE ON SCHEMA public TO "{self.role}";'
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{self.role}";'
                f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{self.role}";'
            )
        role = self.role

        async def setup(conn):
            if role:
                await conn.execute(f'SET ROLE "{role}"')

        self.pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2, setup=setup)
        o = self.owner
        await o.execute(
            "INSERT INTO farms (farm_id, tenant_id, name) VALUES ($1, $2::uuid, 'Inventory farm')",
            self.farm_id,
            self.tenant,
        )
        for item, batch, tenant in (
            (self.item_id, self.batch_id, self.tenant),
            (self.foreign_item, self.foreign_batch, self.other_tenant),
        ):
            await o.execute(
                "INSERT INTO inventory_items (item_id, tenant_id, category, name, unit)"
                " VALUES ($1, $2::uuid, 'fertilizer', 'Inventory item', 'kg')",
                item,
                tenant,
            )
            await o.execute(
                "INSERT INTO inventory_batches (batch_id, tenant_id, item_id, quantity, unit)"
                " VALUES ($1, $2::uuid, $3, 10, 'kg')",
                batch,
                tenant,
                item,
            )
        return self

    async def stock(self, batch_id: str | None = None) -> float:
        value = await self.owner.fetchval(
            "SELECT quantity FROM inventory_batches WHERE batch_id = $1", batch_id or self.batch_id
        )
        return float(value)

    async def operations(self) -> int:
        return await self.owner.fetchval(
            "SELECT count(*) FROM farm_operation_ledger WHERE farm_id = $1", self.farm_id
        )

    async def __aexit__(self, *exc):
        o = self.owner
        try:
            await o.execute(
                "DELETE FROM commands WHERE tenant_id = ANY($1::uuid[])",
                [self.tenant, self.other_tenant],
            )
            await o.execute("DELETE FROM farm_operation_ledger WHERE farm_id = $1", self.farm_id)
            await o.execute(
                "DELETE FROM inventory_items WHERE item_id = ANY($1::text[])",
                [self.item_id, self.foreign_item],
            )
            await o.execute("DELETE FROM farms WHERE farm_id = $1", self.farm_id)
        finally:
            await self.pool.close()
            if self.role:
                await o.execute(f'DROP OWNED BY "{self.role}"; DROP ROLE "{self.role}"')
            await o.close()


def _request(router, live, *, quantity=4.0, batch=None, status="completed", unit="kg", item=None):
    return router.OperationLedgerIn(
        operation_date=date.today(),
        operation_type="fertilization",
        farm_id=live.farm_id,
        status=status,
        inputs=[
            {
                "input_type": "fertilizer",
                "inventory_item_id": item,
                "inventory_batch_id": batch or live.batch_id,
                "quantity": quantity,
                "unit": unit,
            }
        ],
    )


def _run(monkeypatch, case, *, flag: bool):
    main, router = _platform()
    monkeypatch.setenv("FEATURE_FARM_OPERATIONS_LEDGER", "true")
    if flag:
        monkeypatch.setenv(FLAG, "true")
    else:
        monkeypatch.delenv(FLAG, raising=False)

    async def body():
        async with Live() as live:
            monkeypatch.setattr(main, "_DB_POOL", live.pool)
            await case(live, router)

    asyncio.run(body())


def test_flag_off_records_the_operation_and_moves_no_stock(monkeypatch):
    async def case(live, router):
        out = await router.create_operation_ledger_record(
            _request(router, live), user=_user(live.tenant), idem=str(uuid.uuid4())
        )
        assert out["persisted"] is True
        assert out["inventory_deduction"] == {
            "applied": False,
            "flag": FLAG,
            "disabled_reason": "feature_flag_off",
            "receipts": [],
        }
        assert await live.stock() == 10.0

    _run(monkeypatch, case, flag=False)


def test_flag_on_deducts_the_named_batch_once_and_returns_a_receipt(monkeypatch):
    async def case(live, router):
        user = _user(live.tenant)
        key = str(uuid.uuid4())
        req = _request(router, live, item=live.item_id)
        first = await router.create_operation_ledger_record(req, user=user, idem=key)
        deduction = first["inventory_deduction"]
        assert deduction["applied"] is True
        assert deduction["receipts"] == [
            {
                "operation_id": first["operation_id"],
                "batch_id": live.batch_id,
                "item_id": live.item_id,
                "unit": "kg",
                "quantity_deducted": 4.0,
                "quantity_before": 10.0,
                "quantity_after": 6.0,
            }
        ]
        assert await live.stock() == 6.0
        assert (
            await live.owner.fetchval(
                "SELECT quantity FROM farm_input_records WHERE operation_id = $1",
                first["operation_id"],
            )
            == 4.0
        )

        replay = await router.create_operation_ledger_record(req, user=user, idem=key)
        assert replay == first  # the stored receipt, not a second deduction
        assert await live.stock() == 6.0
        assert await live.operations() == 1

    _run(monkeypatch, case, flag=True)


def test_flag_on_without_idempotency_key_is_refused_before_any_write(monkeypatch):
    from fastapi import HTTPException

    async def case(live, router):
        with pytest.raises(HTTPException) as caught:
            await router.create_operation_ledger_record(
                _request(router, live), user=_user(live.tenant), idem=None
            )
        assert caught.value.status_code == 428
        assert (await live.stock(), await live.operations()) == (10.0, 0)

    _run(monkeypatch, case, flag=True)


@pytest.mark.parametrize(
    ("kwargs", "status", "reason"),
    [
        ({"quantity": 10.5}, 409, "inventory_batch_insufficient_stock"),
        ({"unit": "L"}, 409, "inventory_batch_unit_mismatch"),
        ({"item": "some-other-item"}, 409, "inventory_batch_item_mismatch"),
        ({"status": "planned"}, 409, "inventory_deduction_requires_completed_operation"),
    ],
)
def test_flag_on_refusals_write_nothing(monkeypatch, kwargs, status, reason):
    from fastapi import HTTPException

    async def case(live, router):
        with pytest.raises(HTTPException) as caught:
            await router.create_operation_ledger_record(
                _request(router, live, **kwargs), user=_user(live.tenant), idem=str(uuid.uuid4())
            )
        assert caught.value.status_code == status
        assert caught.value.detail["reason"] == reason
        assert (await live.stock(), await live.operations()) == (10.0, 0)

    _run(monkeypatch, case, flag=True)


def test_concurrent_deductions_cannot_overdraw_the_batch(monkeypatch):
    """Two keys racing for 6 of 10: the row lock serialises them, exactly one is refused."""
    from fastapi import HTTPException

    async def case(live, router):
        user = _user(live.tenant)
        results = await asyncio.gather(
            *(
                router.create_operation_ledger_record(
                    _request(router, live, quantity=6), user=user, idem=str(uuid.uuid4())
                )
                for _ in range(2)
            ),
            return_exceptions=True,
        )
        refused = [r for r in results if isinstance(r, HTTPException)]
        applied = [r for r in results if isinstance(r, dict)]
        assert len(applied) == 1 and len(refused) == 1, results
        assert refused[0].detail["reason"] == "inventory_batch_insufficient_stock"
        assert (await live.stock(), await live.operations()) == (4.0, 1)

    _run(monkeypatch, case, flag=True)


def test_another_tenants_batch_is_not_found_and_untouched(monkeypatch):
    from fastapi import HTTPException

    async def case(live, router):
        with pytest.raises(HTTPException) as caught:
            await router.create_operation_ledger_record(
                _request(router, live, batch=live.foreign_batch),
                user=_user(live.tenant),
                idem=str(uuid.uuid4()),
            )
        assert caught.value.status_code == 404
        assert caught.value.detail["reason"] == "inventory_batch_not_found_for_tenant"
        assert await live.stock(live.foreign_batch) == 10.0
        assert await live.operations() == 0

    _run(monkeypatch, case, flag=True)


def test_preview_with_every_flag_on_writes_nothing(monkeypatch):
    async def case(live, router):
        monkeypatch.setenv("FEATURE_OPERATION_LEDGER_AUTOWRITE", "true")
        monkeypatch.setenv("FEATURE_LEDGER_INVENTORY_SYNC", "true")
        req = router.OperationEventIn(
            occurred_on=date.today(),
            operation_type="fertilization",
            farm_id=live.farm_id,
            inputs=[
                {
                    "resource_type": "fertilizer",
                    "quantity": 4,
                    "unit": "kg",
                    "inventory_item_id": live.item_id,
                }
            ],
        )
        out = await router.operation_autowrite_preview(req, user=_user(live.tenant))
        assert (out["persisted"], out["would_persist"]) == (False, False)
        assert (await live.stock(), await live.operations()) == (10.0, 0)

    _run(monkeypatch, case, flag=True)
