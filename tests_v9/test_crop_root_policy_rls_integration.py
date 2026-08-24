"""RZ-VARIETY runtime RLS evidence: crop_root_policies tenant isolation on live PostgreSQL.

Marked `integration` — needs a live PostgreSQL with migration v169 applied and a
NOSUPERUSER/NOBYPASSRLS role (sahool_app), like the other RLS integration tests;
a superuser bypasses FORCE RLS and would make this vacuously pass.

Static RLS policy text is already guarded; this measures the runtime effect the
variety-aware resolver depends on: tenant A resolving (wheat, imam) gets A's
policy, tenant B gets B's — with both rows present in the same table. The SQL
under test is asserted to be the resolver's own text, so the evidence cannot
silently drift from the production query.
"""

from __future__ import annotations

import inspect
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

_SERVICE_DIR = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

_EXACT_SQL = (
    "SELECT policy_id, initial_depth_m, maximum_depth_m, effective_fraction, "
    "policy_version, evidence_ids, variety FROM crop_root_policies "
    "WHERE tenant_id=$1::uuid AND crop_id=$2 AND variety=$3 "
    "AND status='validated' "
    "AND valid_from <= now() AND (valid_to IS NULL OR valid_to > now()) "
    "ORDER BY valid_from DESC LIMIT 1"
)


def _dsn() -> str:
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn or "sahool_app" not in dsn:
        pytest.skip("DATABASE_URL on the NOBYPASSRLS sahool_app role is required")
    return dsn


def test_exact_tier_sql_is_the_resolver_source_text():
    """Bind the SQL executed below to the resolver's actual production query."""
    import api.canonical_root_zone_profile as module

    source = inspect.getsource(module.resolve_canonical_root_zone_profile)
    compact = " ".join(part.strip().strip('"') for part in source.splitlines())
    assert "variety=$3" in source
    assert "variety=''" in source
    for fragment in (
        "WHERE tenant_id=$1::uuid AND crop_id=$2 AND variety=$3",
        "ORDER BY valid_from DESC LIMIT 1",
    ):
        assert fragment in compact, fragment


async def test_rls_two_tenants_same_crop_variety_resolve_their_own_policy():
    asyncpg = pytest.importorskip("asyncpg")
    dsn = _dsn()

    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    marker = uuid.uuid4().hex[:12]
    inserted = []

    async def _connect(tenant: str):
        conn = await asyncpg.connect(dsn, statement_cache_size=0)
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
        return conn

    async def _seed(tenant: str, policy_id: str, max_depth: float):
        conn = await _connect(tenant)
        try:
            await conn.execute(
                "INSERT INTO crop_root_policies("
                "policy_id, tenant_id, crop_id, variety, initial_depth_m, maximum_depth_m, "
                "effective_fraction, policy_version, evidence_ids, status, valid_from) "
                "VALUES($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8,$9::jsonb,'validated',now())",
                policy_id,
                tenant,
                f"wheat-{marker}",
                "imam",
                0.2,
                max_depth,
                0.8,
                "v1",
                '["evidence-rls"]',
            )
            inserted.append((tenant, policy_id))
        finally:
            await conn.close()

    pol_a, pol_b = str(uuid.uuid4()), str(uuid.uuid4())
    await _seed(tenant_a, pol_a, 1.20)
    await _seed(tenant_b, pol_b, 0.90)

    try:
        for tenant, expected_policy, expected_max in (
            (tenant_a, pol_a, 1.20),
            (tenant_b, pol_b, 0.90),
        ):
            conn = await _connect(tenant)
            try:
                row = await conn.fetchrow(_EXACT_SQL, tenant, f"wheat-{marker}", "imam")
                assert row is not None
                assert str(row["policy_id"]) == expected_policy
                assert float(row["maximum_depth_m"]) == expected_max
                # Cross-tenant probe: the OTHER tenant's id under THIS session GUC
                # must yield nothing — RLS, not the WHERE clause, is the boundary.
                other = tenant_b if tenant == tenant_a else tenant_a
                leak = await conn.fetchrow(_EXACT_SQL, other, f"wheat-{marker}", "imam")
                assert leak is None
            finally:
                await conn.close()
    finally:
        for tenant, policy_id in inserted:
            conn = await _connect(tenant)
            try:
                await conn.execute(
                    "DELETE FROM crop_root_policies WHERE tenant_id=$1::uuid AND policy_id=$2::uuid",
                    tenant,
                    policy_id,
                )
            finally:
                await conn.close()
