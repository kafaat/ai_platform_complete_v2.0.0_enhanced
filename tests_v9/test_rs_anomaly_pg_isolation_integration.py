"""RS-6 integration test: real-PostgreSQL RLS tenant isolation for the anomaly store.

Marked `integration` — runs only when a live PostgreSQL + PostGIS with the v191
migration applied is available (staging/CI integration job), never in the unit
gate. It seeds two tenants and proves a tenant cannot read or transition another
tenant's anomaly even holding its anomaly_ref — the DB (FORCE RLS) enforces it.

Requires a NOSUPERUSER/NOBYPASSRLS role (sahool_app) so RLS is actually observed;
a superuser bypasses FORCE RLS and would make the test vacuously pass.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

_SERVICE_DIR = Path(__file__).resolve().parents[1] / "services" / "vegetation-analysis-service"
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))


def _dsn() -> str:
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn or "sahool_app" not in dsn:
        pytest.skip("DATABASE_URL on the NOBYPASSRLS sahool_app role is required")
    return dsn


def _anomaly_payload(tenant: str, ref: str) -> dict:
    return {
        "anomaly_ref": ref,
        "tenant_id": tenant,
        "field_id": "fld_iso",
        "season_id": "sea_iso",
        "signal_type": "ndvi_decline",
        "severity": "high",
        "confidence": "0.8",
        "deviation": "-0.2",
    }


@pytest.mark.asyncio
async def test_cross_tenant_read_and_transition_are_blocked_by_rls():
    from anomaly_store import AnomalyNotFound
    from anomaly_store_pg import PostgresAnomalyStore

    store = PostgresAnomalyStore(_dsn())
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    ref = f"urn:sahool:anomaly:iso_{uuid.uuid4().hex[:16]}"

    created = await store.upsert_detected(_anomaly_payload(tenant_a, ref))
    assert created["tenant_id"] == tenant_a

    # Tenant A reads its own anomaly.
    got = await store.get(ref, tenant_id=tenant_a)
    assert got["anomaly_ref"] == ref

    # Tenant B cannot observe tenant A's anomaly even with the exact ref.
    with pytest.raises(AnomalyNotFound):
        await store.get(ref, tenant_id=tenant_b)

    # Tenant B cannot transition tenant A's anomaly.
    with pytest.raises(AnomalyNotFound):
        await store.transition(ref, "triaged", expected_version=1, tenant_id=tenant_b)

    # Tenant A's own transition succeeds and bumps the version.
    moved = await store.transition(ref, "triaged", expected_version=1, tenant_id=tenant_a)
    assert moved["status"] == "triaged"
    assert moved["aggregate_version"] == 2
