"""Exercise both equipment list shapes and the maintenance join on PostgreSQL."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


async def test_equipment_schedule_wiring(monkeypatch):
    import asyncpg
    from api import main
    from api.routers.equipment import list_equipment
    from core.canonical_schemas import UserRole, UserSchema

    tenant, other_tenant = uuid4(), uuid4()
    user = UserSchema(
        user_id=str(uuid4()), tenant_id=str(tenant), role=UserRole.MANAGER, name_ar="مراجع"
    )
    # Use one real session so both calls see its temporary copies of the migrated
    # tables. The foreign maintenance row is visible to SQL: the join itself must
    # exclude it, independently of RLS on the production tables.
    async with asyncpg.create_pool(os.environ["TEST_DATABASE_URL"], min_size=1, max_size=1) as pool:
        monkeypatch.setattr(main, "_DB_POOL", pool)
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TEMP TABLE equipment (LIKE public.equipment INCLUDING DEFAULTS);
                CREATE TEMP TABLE equipment_maintenance
                    (LIKE public.equipment_maintenance INCLUDING DEFAULTS);
            """)
            await conn.execute(
                """
                INSERT INTO equipment (equipment_id, tenant_id, name, type, operating_hours)
                VALUES ('pump-a', $1, 'Pump A', 'pump', 300),
                       ('pump-b', $1, 'Pump B', 'pump', 100)
            """,
                tenant,
            )
            await conn.execute(
                """
                INSERT INTO equipment_maintenance
                    (maintenance_id, equipment_id, tenant_id, kind, status, scheduled_date, performed_date)
                VALUES ('later', 'pump-a', $1, 'scheduled', 'planned', DATE '2002-01-01', NULL),
                       ('first', 'pump-a', $1, 'scheduled', 'planned', DATE '2001-01-01', NULL),
                       ('foreign', 'pump-a', $2, 'scheduled', 'planned', DATE '2000-01-01', NULL),
                       ('done', 'pump-b', $1, 'scheduled', 'done', DATE '2000-01-01', DATE '2000-01-01'),
                       ('cancelled', 'pump-b', $1, 'scheduled', 'cancelled', DATE '2000-01-01', NULL),
                       ('repair', 'pump-b', $1, 'repair', 'planned', DATE '2000-01-01', NULL),
                       ('performed', 'pump-b', $1, 'scheduled', 'planned', DATE '2000-01-01', DATE '2000-01-01'),
                       ('undated', 'pump-b', $1, 'scheduled', 'planned', NULL, NULL)
            """,
                tenant,
                other_tenant,
            )

        legacy = await list_equipment(user=user, summary=False)
        summary = await list_equipment(user=user, summary=True)

    assert [asset["equipment_id"] for asset in legacy] == ["pump-a", "pump-b"]
    assert all(
        set(asset) == {"equipment_id", "name", "type", "status", "operating_hours", "purchase_date"}
        for asset in legacy
    )
    assert summary["assets"] == [dict(legacy[0], next_service_date="2001-01-01"), legacy[1]]
    assert summary["intelligence"]["due_asset_ids"] == ["pump-a"]
    assert summary["intelligence"]["not_evaluated_asset_ids"] == ["pump-b"]
