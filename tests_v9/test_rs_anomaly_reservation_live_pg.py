"""Ground-verification reservation on the PostgreSQL anomaly store (live PG, v191 table).

SCOUTING-ANOMALY-VERIFY-RACE-ORPHAN-TASK-01: the verification route used to create the
field-management scouting task *before* the versioned anomaly transition, so a resolve racing
the dispatch could leave a pending task no anomaly pointed at. The route now reserves the
verification against the expected version first (``reserve_verification``), dispatches, then
attaches the task (``attach_verification_task``) or gives the reservation back
(``release_verification_reservation``). This file proves the PostgreSQL store's half of that on a
real database, as the NOBYPASSRLS application role, under FORCE RLS: a racing resolve is refused
while the reservation is pending, concurrent reservations have one winner, a release restores the
prior state, and the operations stay tenant-bound.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

_CERTIFICATION_REQUIRED = os.getenv("ANOMALY_RESERVATION_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
except ImportError:
    if _CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg")

_SERVICE_DIR = Path(__file__).resolve().parents[1] / "services" / "vegetation-analysis-service"
DSN = os.getenv("TEST_DATABASE_URL", "")
KEY = "r" * 64


async def _probe() -> str:
    if not DSN:
        return "TEST_DATABASE_URL is not set"
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        if await conn.fetchval("SELECT to_regclass('public.signal_anomalies')") is None:
            return "schema not migrated (signal_anomalies missing)"
        if await conn.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ):
            return "TEST_DATABASE_URL bypasses RLS; the store must be measured as the app role"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
if _WHY and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        f"ANOMALY_RESERVATION_CERTIFICATION_REQUIRED=1 but the live database is unusable: {_WHY}"
    )
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _store_module():
    service_dir = str(_SERVICE_DIR)
    while service_dir in sys.path:
        sys.path.remove(service_dir)
    sys.path.insert(0, service_dir)
    import anomaly_store
    import anomaly_store_pg

    return anomaly_store, anomaly_store_pg


async def _seeded(tenant: str | None = None):
    anomaly_store, anomaly_store_pg = _store_module()
    store = anomaly_store_pg.PostgresAnomalyStore(DSN)
    tenant = tenant or str(uuid.uuid4())
    ref = f"urn:sahool:anomaly:resv_{uuid.uuid4().hex[:16]}"
    created = await store.upsert_detected(
        {
            "anomaly_ref": ref,
            "tenant_id": tenant,
            "field_id": "fld_resv",
            "season_id": "sea_resv",
            "signal_type": "ndvi_decline",
            "severity": "high",
        }
    )
    assert created["aggregate_version"] == 1, created
    return anomaly_store, store, tenant, ref


@pytest.mark.asyncio
async def test_a_resolve_racing_the_dispatch_is_refused_and_the_task_attaches():
    anomaly_store, store, tenant, ref = await _seeded()
    try:
        reserved = await store.reserve_verification(
            ref, expected_version=1, idempotency_key=KEY, tenant_id=tenant
        )
        assert reserved["status"] == "verification_requested", reserved
        assert reserved["task_ref"] is None, "no task exists while the dispatch runs"
        assert reserved["payload"]["verification_reservation"]["state"] == "pending", reserved
        # The dispatch is in flight: resolves with the old and with the current version, and a
        # verification result, all race it concurrently. Every one must be refused.
        racers = await asyncio.gather(
            store.transition(ref, "resolved", expected_version=1, tenant_id=tenant),
            store.transition(ref, "resolved", expected_version=2, tenant_id=tenant),
            store.transition(ref, "rejected", expected_version=2, tenant_id=tenant),
            return_exceptions=True,
        )
        reasons = sorted(str(r) for r in racers)
        assert all(isinstance(r, anomaly_store.InvalidTransition) for r in racers), racers
        assert reasons == [
            "aggregate_version_conflict",
            "verification_reservation_pending",
            "verification_reservation_pending",
        ], reasons
        attached = await store.attach_verification_task(
            ref,
            expected_version=2,
            idempotency_key=KEY,
            task_ref="urn:sahool:task:t-live",
            tenant_id=tenant,
        )
        assert attached["task_ref"] == "urn:sahool:task:t-live", attached
        assert attached["payload"]["verification_reservation"]["state"] == "attached", attached
        confirmed = await store.transition(ref, "confirmed", expected_version=3, tenant_id=tenant)
        assert confirmed["status"] == "confirmed", "the lifecycle resumes after the attach"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_concurrent_reservations_have_one_winner():
    anomaly_store, store, tenant, ref = await _seeded()
    try:
        results = await asyncio.gather(
            *(
                store.reserve_verification(
                    ref, expected_version=1, idempotency_key=KEY, tenant_id=tenant
                )
                for _ in range(5)
            ),
            return_exceptions=True,
        )
        winners = [r for r in results if isinstance(r, dict)]
        losers = [str(r) for r in results if isinstance(r, anomaly_store.InvalidTransition)]
        assert len(winners) == 1, results
        assert losers == ["aggregate_version_conflict"] * 4, results
        current = await store.get(ref, tenant_id=tenant)
        assert current["aggregate_version"] == 2, "exactly one reservation was written"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_a_release_restores_the_prior_state():
    anomaly_store, store, tenant, ref = await _seeded()
    try:
        await store.transition(ref, "triaged", expected_version=1, tenant_id=tenant)
        await store.reserve_verification(
            ref, expected_version=2, idempotency_key=KEY, tenant_id=tenant
        )
        released = await store.release_verification_reservation(
            ref,
            expected_version=3,
            idempotency_key=KEY,
            reason="task_service_rejected:422",
            tenant_id=tenant,
        )
        assert released["status"] == "triaged", released
        assert released["task_ref"] is None, released
        assert "verification_reservation" not in released["payload"], released["payload"]
        resolved = await store.transition(ref, "resolved", expected_version=4, tenant_id=tenant)
        assert resolved["status"] == "resolved", "a released anomaly is open again"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_another_tenant_cannot_reserve_attach_or_release():
    anomaly_store, store, tenant, ref = await _seeded()
    other = str(uuid.uuid4())
    try:
        with pytest.raises(anomaly_store.AnomalyNotFound):
            await store.reserve_verification(
                ref, expected_version=1, idempotency_key=KEY, tenant_id=other
            )
        await store.reserve_verification(
            ref, expected_version=1, idempotency_key=KEY, tenant_id=tenant
        )
        with pytest.raises(anomaly_store.AnomalyNotFound):
            await store.attach_verification_task(
                ref,
                expected_version=2,
                idempotency_key=KEY,
                task_ref="urn:sahool:task:t-x",
                tenant_id=other,
            )
        with pytest.raises(anomaly_store.AnomalyNotFound):
            await store.release_verification_reservation(
                ref, expected_version=2, idempotency_key=KEY, reason="x", tenant_id=other
            )
        current = await store.get(ref, tenant_id=tenant)
        assert current["payload"]["verification_reservation"]["state"] == "pending", current
    finally:
        await store.close()
