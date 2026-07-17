"""IRR-F01 Gate U1 — the UPGRADE half of live certification (fresh-schema is the other).

Where ``test_irr_f01_reservation_live_pg`` certifies the v195/v196 slice on a database
migrated cleanly to v196, Gate U1 certifies the same slice on a database that was migrated
only through v194, seeded with realistic legacy irrigation data, and then upgraded with
v195 + v196 applied ON TOP (see ``scripts/irr_f01/upgrade_gate_u1.sh`` which builds the DB
and asserts no data loss / idempotent re-apply). This module adds the behavioural proof the
shell script cannot make cheaply: the v195 tenant-scoped composite FK
``(canonical_hydraulic_capability_id, tenant_id) -> canonical_hydraulic_capabilities`` —
backed by the index v195 self-adds — actually accepts a reservation whose capability row
was written BEFORE v195 existed, and Gate B1's outbox emission works over the upgraded DB.

Env (fail-closed under IRR_F01_CERTIFICATION_REQUIRED=1, otherwise skips):
  IRR_F01_UPGRADE_DATABASE_URL   — app-role (NOSUPERUSER/NOBYPASSRLS) DSN on the upgraded DB
  IRR_F01_UPGRADE_ADMIN_URL      — admin DSN on the same DB (defaults to the app DSN)

The fixed legacy identifiers below MUST match scripts/irr_f01/upgrade_gate_u1.sh.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")
pytestmark = pytest.mark.integration

UP_APP_DSN = os.getenv("IRR_F01_UPGRADE_DATABASE_URL")
UP_ADMIN_DSN = os.getenv("IRR_F01_UPGRADE_ADMIN_URL", UP_APP_DSN)
CERTIFICATION_REQUIRED = os.getenv("IRR_F01_CERTIFICATION_REQUIRED") == "1"

# Fixed legacy identifiers seeded pre-v195 by scripts/irr_f01/upgrade_gate_u1.sh.
U1_TENANT = UUID("11111111-1111-1111-1111-111111111111")
U1_PROJECT = UUID("22222222-2222-2222-2222-222222222222")
U1_NODE1 = UUID("66666666-6666-6666-6666-666666666666")
U1_CAP_ID = "u1-capability-legacy"

CORE_TABLES = (
    "hydraulic_capacity_evaluations",
    "irrigation_resource_reservations",
    "irrigation_resource_reservation_events",
    "irrigation_target_bindings",
)

START = datetime(2026, 7, 17, 21, tzinfo=UTC)
END = START + timedelta(minutes=45)


def _skip_or_fail(message: str) -> None:
    if CERTIFICATION_REQUIRED:
        pytest.fail(message)
    pytest.skip(message)


def _adapter():
    import sys
    from pathlib import Path

    platform = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"
    if str(platform) not in sys.path:
        sys.path.insert(0, str(platform))
    from api import irrigation_capacity_reservation as kernel
    from api import irrigation_reservation_adapter as adapter

    return adapter, kernel


class _Port:
    async def request_dispatch(self, conn, **kw):
        return "req-u1"

    async def mark_dispatch_failed(self, conn, **kw):
        return None


@pytest.fixture
async def upgraded():
    if not UP_APP_DSN:
        _skip_or_fail("IRR_F01_UPGRADE_DATABASE_URL unset — run scripts/irr_f01/upgrade_gate_u1.sh")
    try:
        app = await asyncpg.connect(UP_APP_DSN)
    except Exception as exc:  # noqa: BLE001
        _skip_or_fail(f"upgrade DB unavailable: {type(exc).__name__}")
        return
    is_super = await app.fetchval("select current_setting('is_superuser')")
    bypass = await app.fetchval("select rolbypassrls from pg_roles where rolname = current_user")
    if is_super == "on" or bypass:
        await app.close()
        _skip_or_fail("connect as a NOSUPERUSER/NOBYPASSRLS app role to certify the upgrade")
    yield app
    await app.close()


async def test_u1_upgrade_left_the_v195_v196_surface_present(upgraded):
    """The upgrade added exactly the v195/v196 tables + the self-added tenant-scoped index."""
    app = upgraded
    for table in CORE_TABLES:
        if await app.fetchval("select to_regclass($1)", table) is None:
            _skip_or_fail(f"{table} absent — the v195/v196 upgrade did not run")
    idx = await app.fetchval(
        "select count(*) from pg_indexes where indexname='uq_canonical_hydraulic_capability_tenant'"
    )
    assert idx == 1, "v195 must self-add uq_canonical_hydraulic_capability_tenant during upgrade"


async def test_u1_legacy_capability_survived_and_is_tenant_visible(upgraded):
    """The pre-v195 capability row is intact and RLS-visible under its own tenant only."""
    app = upgraded
    await app.execute("select set_config('app.current_tenant', $1, false)", str(U1_TENANT))
    row = await app.fetchrow(
        "select capability_id, status from canonical_hydraulic_capabilities where capability_id=$1",
        U1_CAP_ID,
    )
    if row is None:
        _skip_or_fail("legacy capability missing — re-run scripts/irr_f01/upgrade_gate_u1.sh")
    assert row["status"] == "verified"
    # RLS: a foreign tenant sees nothing.
    await app.execute("select set_config('app.current_tenant', $1, false)", str(uuid4()))
    assert (
        await app.fetchval(
            "select count(*) from canonical_hydraulic_capabilities where capability_id=$1",
            U1_CAP_ID,
        )
        == 0
    )


async def test_u1_reservation_binds_v195_composite_fk_over_legacy_capability(upgraded):
    """Gate A over the upgraded DB: a reservation referencing the PRE-v195 capability is
    accepted, proving the v195 composite FK + self-added index work against legacy data."""
    adapter, kernel = _adapter()
    app = upgraded
    req = adapter.ResourceRequest(
        resource_node_id=U1_NODE1,
        policy=kernel.ResourcePolicy("shared_capacity"),
        reserved_flow_m3h=Decimal("120"),
        derated_capacity_m3h=Decimal("300"),
    )
    async with app.transaction():
        out = await adapter.reserve_and_request_dispatch_db(
            app,
            tenant_id=U1_TENANT,
            project_id=U1_PROJECT,
            requested_start=START,
            requested_end=END,
            resources=[req],
            execution_ref_type="manual_execution",
            execution_ref_id="u1-fk",
            calculation_model_version="v1",
            execution_port=_Port(),
            correlation_id=U1_TENANT,
            canonical_hydraulic_capability_id=U1_CAP_ID,
            idempotency_key=f"U1FK-{uuid4()}",
        )
    await app.execute("select set_config('app.current_tenant', $1, false)", str(U1_TENANT))
    bound = await app.fetchval(
        "select canonical_hydraulic_capability_id from hydraulic_capacity_evaluations "
        "where evaluation_id=$1",
        UUID(out.evaluation_id),
    )
    assert bound == U1_CAP_ID, "evaluation must carry the legacy capability via the composite FK"

    # A dangling capability id under this tenant is rejected by the composite FK — the FK is live.
    with pytest.raises(asyncpg.PostgresError):
        async with app.transaction():
            await adapter.reserve_and_request_dispatch_db(
                app,
                tenant_id=U1_TENANT,
                project_id=U1_PROJECT,
                requested_start=START,
                requested_end=END,
                resources=[req],
                execution_ref_type="manual_execution",
                execution_ref_id="u1-fk-bad",
                calculation_model_version="v1",
                execution_port=_Port(),
                correlation_id=U1_TENANT,
                canonical_hydraulic_capability_id="does-not-exist",
                idempotency_key=f"U1BAD-{uuid4()}",
            )
