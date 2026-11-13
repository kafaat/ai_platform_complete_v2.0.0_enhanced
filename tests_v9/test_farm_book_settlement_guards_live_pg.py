"""A credit entry's payable stays traceable: settlement and reversal guards (live PG).

This replaces an AsyncMock test in services/sahool-platform/tests/test_simple_farm_book.py
whose mock answered every lookup with "a conflicting child exists". Here ``create_entry`` runs
against a migrated Postgres through a NOBYPASSRLS role, with the rows really present:

- a payment cannot settle a reversal (cannot_settle_a_reversal, 422);
- a payment cannot settle a reversed entry (cannot_settle_reversed_entry, 409);
- a settled credit entry cannot be reversed (cannot_reverse_entry_with_settlements, 409);

and in each case nothing is stored. A payment of an open credit is stored (the control).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

asyncpg = pytest.importorskip("asyncpg")
pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in ("farm_ledger_entries", "farm_ledger_parties", "farms"):
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _modules():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main
    from api.routers import simple_farm_book as book

    return main, book


class Live:
    def __init__(self):
        tag = uuid.uuid4().hex[:8]
        self.tenant = str(uuid.uuid4())
        self.farm = f"sg-farm-{tag}"
        self.party = f"sg-party-{tag}"
        self.role: str | None = None

    async def __aenter__(self):
        self.owner = await asyncpg.connect(DSN)
        if await self.owner.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ):
            self.role = f"sg_rls_{uuid.uuid4().hex[:10]}"
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
        await self.owner.execute(
            "INSERT INTO farms (farm_id, tenant_id, name) VALUES ($1, $2::uuid, $1)",
            self.farm,
            self.tenant,
        )
        await self.owner.execute(
            "INSERT INTO farm_ledger_parties (party_id, tenant_id, party_type, name)"
            " VALUES ($1, $2::uuid, 'supplier', $1)",
            self.party,
            self.tenant,
        )
        return self

    async def __aexit__(self, *exc):
        o = self.owner
        try:
            async with o.transaction():
                if await o.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"):
                    # The ledger is append-only by trigger (v211); see the receipt-scope test.
                    await o.execute("SET LOCAL session_replication_role = replica")
                    for table in ("farm_ledger_entries", "farm_ledger_parties", "farms"):
                        await o.execute(
                            f"DELETE FROM {table} WHERE tenant_id = $1::uuid", self.tenant
                        )
        finally:
            await self.pool.close()
            if self.role:
                await o.execute(f'DROP OWNED BY "{self.role}"; DROP ROLE "{self.role}"')
            await o.close()

    async def stored(self, client_operation_id: str) -> bool:
        return bool(
            await self.owner.fetchval(
                "SELECT count(*) FROM farm_ledger_entries"
                " WHERE tenant_id = $1::uuid AND client_operation_id = $2",
                self.tenant,
                client_operation_id,
            )
        )


def _user(tenant: str):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(user_id="sg-owner", tenant_id=tenant, role=UserRole.OWNER, name_ar="مالك")


def _run(monkeypatch, case):
    main, book = _modules()

    async def body():
        async with Live() as live:
            monkeypatch.setattr(main, "_DB_POOL", live.pool)
            await case(live, book, _user(live.tenant))

    asyncio.run(body())


def _credit(book, live, **extra):
    return book.SimpleEntryIn(
        client_operation_id=f"sg-op-{uuid.uuid4().hex}",
        entry_type="expense",
        payment_method="credit",
        category="repair",
        amount=Decimal("100"),
        occurred_on=date(2026, 11, 12),
        farm_id=live.farm,
        party_id=live.party,
        **extra,
    )


def _payment(book, live, settles: str, amount: str = "40"):
    return book.SimpleEntryIn(
        client_operation_id=f"sg-op-{uuid.uuid4().hex}",
        entry_type="payment",
        payment_method="cash",
        category="debt_payment",
        amount=Decimal(amount),
        occurred_on=date(2026, 11, 13),
        farm_id=live.farm,
        party_id=live.party,
        settles_entry_id=settles,
    )


async def _refused(book, req, user) -> tuple[int, str]:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        await book.create_entry(req, user=user)
    return caught.value.status_code, caught.value.detail


def test_paying_a_reversal_or_a_reversed_entry_is_refused(monkeypatch):
    async def case(live, book, user):
        debt = await book.create_entry(_credit(book, live), user=user)
        reversal = await book.create_entry(
            _credit(book, live, reverses_entry_id=debt["entry_id"]), user=user
        )
        on_reversal = _payment(book, live, reversal["entry_id"])
        assert await _refused(book, on_reversal, user) == (422, "cannot_settle_a_reversal")
        on_reversed = _payment(book, live, debt["entry_id"])
        assert await _refused(book, on_reversed, user) == (409, "cannot_settle_reversed_entry")
        assert not await live.stored(on_reversal.client_operation_id)
        assert not await live.stored(on_reversed.client_operation_id)

    _run(monkeypatch, case)


def test_reversing_a_settled_credit_entry_is_refused(monkeypatch):
    async def case(live, book, user):
        debt = await book.create_entry(_credit(book, live), user=user)
        paid = await book.create_entry(_payment(book, live, debt["entry_id"]), user=user)
        assert paid["persisted"] is True
        reversal = _credit(book, live, reverses_entry_id=debt["entry_id"])
        assert await _refused(book, reversal, user) == (
            409,
            "cannot_reverse_entry_with_settlements",
        )
        assert not await live.stored(reversal.client_operation_id)

    _run(monkeypatch, case)
