"""The farm-book write path keeps an entry, its field and its receipt on one farm (live PG).

The unit tests in ``test_farm_book_receipt_field.py`` check the decisions as pure functions.
This file drives ``create_entry`` itself against a migrated Postgres, through a pool that runs
as a NOBYPASSRLS role, because the hole found in review lived between the decisions: a
manager limited to farm X posted an entry on farm X naming a field of farm Y with that
field's receipt, and every check passed (the field was checked against the tenant only, and
the permission against the farm the caller named).

Tenant A has farm X (field fX, receipt docX) and farm Y (field fY, receipt docY), plus a
receipt with no field (shared).
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
        for table in ("farm_ledger_entries", "documents", "farms"):
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


def _user(tenant: str, role: str, farms: list[str] | None = None):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id=f"u-{uuid.uuid4().hex[:8]}",
        tenant_id=tenant,
        role=UserRole(role),
        name_ar="مستخدم",
        farm_ids_access=farms or [],
    )


class Live:
    """Owner connection for setup/measurement + a pool that runs as a NOBYPASSRLS role."""

    def __init__(self):
        tag = uuid.uuid4().hex[:8]
        self.tenant = str(uuid.uuid4())
        self.farm_x, self.farm_y = f"rx-farm-x-{tag}", f"rx-farm-y-{tag}"
        self.field_x, self.field_y = f"rx-field-x-{tag}", f"rx-field-y-{tag}"
        self.doc_x, self.doc_y, self.doc_shared = (
            f"rx-doc-x-{tag}",
            f"rx-doc-y-{tag}",
            f"rx-doc-s-{tag}",
        )
        self.party = f"rx-party-{tag}"
        self.role: str | None = None

    async def __aenter__(self):
        self.owner = await asyncpg.connect(DSN)
        if await self.owner.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ):
            self.role = f"rx_rls_{uuid.uuid4().hex[:10]}"
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
        for farm in (self.farm_x, self.farm_y):
            await o.execute(
                "INSERT INTO farms (farm_id, tenant_id, name) VALUES ($1, $2::uuid, $1)",
                farm,
                self.tenant,
            )
        for field, farm in ((self.field_x, self.farm_x), (self.field_y, self.farm_y)):
            await o.execute(
                "INSERT INTO fields (field_id, name, tenant_id, farm_id) VALUES ($1, $1, $2::uuid, $3)",
                field,
                self.tenant,
                farm,
            )
        await o.execute(
            "INSERT INTO farm_ledger_parties (party_id, tenant_id, party_type, name)"
            " VALUES ($1, $2::uuid, 'supplier', $1)",
            self.party,
            self.tenant,
        )
        for doc, field in (
            (self.doc_x, self.field_x),
            (self.doc_y, self.field_y),
            (self.doc_shared, None),
        ):
            await o.execute(
                """INSERT INTO documents (doc_id, tenant_id, category, field_id, title)
                   VALUES ($1, $2::uuid, 'image', $3, $1)""",
                doc,
                self.tenant,
                field,
            )
        return self

    async def __aexit__(self, *exc):
        o = self.owner
        try:
            # The ledger is append-only by trigger (v211). A superuser (the CI database user)
            # may suspend triggers for this one transaction to remove the test's own tenant;
            # any other role leaves the rows, which belong to a random tenant id.
            async with o.transaction():
                if await o.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"):
                    await o.execute("SET LOCAL session_replication_role = replica")
                    await o.execute(
                        "DELETE FROM farm_ledger_entries WHERE tenant_id = $1::uuid", self.tenant
                    )
                    for table in ("farm_ledger_parties", "documents", "fields", "farms"):
                        await o.execute(
                            f"DELETE FROM {table} WHERE tenant_id = $1::uuid", self.tenant
                        )
        finally:
            await self.pool.close()
            if self.role:
                await o.execute(f'DROP OWNED BY "{self.role}"; DROP ROLE "{self.role}"')
            await o.close()

    async def stored(self, client_operation_id: str):
        return await self.owner.fetchrow(
            "SELECT farm_id, field_id, receipt_document_id FROM farm_ledger_entries"
            " WHERE tenant_id = $1::uuid AND client_operation_id = $2",
            self.tenant,
            client_operation_id,
        )


def _entry(book, farm_id: str, field_id: str | None, receipt: str | None):
    return book.SimpleEntryIn(
        client_operation_id=f"rx-op-{uuid.uuid4().hex}",
        entry_type="expense",
        category="fertilizer",
        amount=Decimal("1500"),
        occurred_on=date(2026, 11, 12),
        farm_id=farm_id,
        field_id=field_id,
        receipt_document_id=receipt,
    )


def _run(monkeypatch, case):
    main, book = _modules()

    async def body():
        async with Live() as live:
            monkeypatch.setattr(main, "_DB_POOL", live.pool)
            await case(live, book)

    asyncio.run(body())


async def _refused(book, req, user) -> tuple[int, str]:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        await book.create_entry(req, user=user)
    return caught.value.status_code, caught.value.detail


def test_review_repro_another_farms_field_and_receipt_on_my_farm_is_refused(monkeypatch):
    async def case(live, book):
        manager = _user(live.tenant, "manager", farms=[live.farm_x])
        req = _entry(book, live.farm_x, live.field_y, live.doc_y)
        assert await _refused(book, req, manager) == (422, "field_not_in_farm")
        assert await live.stored(req.client_operation_id) is None

    _run(monkeypatch, case)


def test_a_field_of_another_farm_is_refused_even_without_a_receipt(monkeypatch):
    async def case(live, book):
        owner = _user(live.tenant, "owner")
        req = _entry(book, live.farm_x, live.field_y, None)
        assert await _refused(book, req, owner) == (422, "field_not_in_farm")
        assert await live.stored(req.client_operation_id) is None

    _run(monkeypatch, case)


def test_a_farm_restricted_user_cannot_write_on_another_farm(monkeypatch):
    async def case(live, book):
        manager = _user(live.tenant, "manager", farms=[live.farm_x])
        req = _entry(book, live.farm_y, live.field_y, None)
        assert await _refused(book, req, manager) == (403, "farm_access_denied")
        assert await live.stored(req.client_operation_id) is None

    _run(monkeypatch, case)


def test_a_receipt_of_another_field_on_the_same_farm_is_refused(monkeypatch):
    async def case(live, book):
        owner = _user(live.tenant, "owner")
        req = _entry(book, live.farm_y, live.field_y, live.doc_x)
        assert await _refused(book, req, owner) == (422, "receipt_field_mismatch")
        assert await live.stored(req.client_operation_id) is None

    _run(monkeypatch, case)


def test_my_farms_field_with_its_own_receipt_is_stored(monkeypatch):
    async def case(live, book):
        manager = _user(live.tenant, "manager", farms=[live.farm_x])
        req = _entry(book, live.farm_x, live.field_x, live.doc_x)
        out = await book.create_entry(req, user=manager)
        assert out["persisted"] is True
        row = await live.stored(req.client_operation_id)
        assert (row["farm_id"], row["field_id"], row["receipt_document_id"]) == (
            live.farm_x,
            live.field_x,
            live.doc_x,
        )

    _run(monkeypatch, case)


def test_a_shared_receipt_backs_a_farm_level_entry(monkeypatch):
    async def case(live, book):
        manager = _user(live.tenant, "manager", farms=[live.farm_x])
        req = _entry(book, live.farm_x, None, live.doc_shared)
        out = await book.create_entry(req, user=manager)
        assert out["persisted"] is True
        row = await live.stored(req.client_operation_id)
        assert row["receipt_document_id"] == live.doc_shared

    _run(monkeypatch, case)


def test_a_payment_cannot_settle_another_farms_credit(monkeypatch):
    async def case(live, book):
        owner = _user(live.tenant, "owner")
        credit = book.SimpleEntryIn(
            client_operation_id=f"rx-op-{uuid.uuid4().hex}",
            entry_type="expense",
            payment_method="credit",
            category="fertilizer",
            amount=Decimal("1000"),
            occurred_on=date(2026, 11, 12),
            farm_id=live.farm_y,
            party_id=live.party,
        )
        debt = await book.create_entry(credit, user=owner)

        def payment(farm_id: str):
            return book.SimpleEntryIn(
                client_operation_id=f"rx-op-{uuid.uuid4().hex}",
                entry_type="payment",
                payment_method="cash",
                category="debt_payment",
                amount=Decimal("400"),
                occurred_on=date(2026, 11, 13),
                farm_id=farm_id,
                party_id=live.party,
                settles_entry_id=debt["entry_id"],
            )

        cross = payment(live.farm_x)
        assert await _refused(book, cross, owner) == (422, "payment_farm_mismatch")
        assert await live.stored(cross.client_operation_id) is None
        same = payment(live.farm_y)
        assert (await book.create_entry(same, user=owner))["persisted"] is True

    _run(monkeypatch, case)
