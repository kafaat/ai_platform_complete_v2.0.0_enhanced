"""Behavioral proof (real Postgres): the PRE-CUTOVER role-certification tool's VERDICT is correct.

``decision_sor_role_certify.py`` is the mandatory precursor to the DECISION-SOR REVOKE — an operator
runs it to confirm the platform and decision-service connect as DIFFERENT Postgres roles before any
REVOKE. A certification is only useful if its verdict is trustworthy, so this test proves the tool:

  * reports ``role_separation_confirmed = True`` and the two distinct current_users when the platform
    and decision-service connections use DIFFERENT login roles;
  * reports ``role_separation_confirmed = False`` when both connections resolve to the SAME role
    (the "do not REVOKE — it would break both services" signal);
  * surfaces the role attributes (``rolsuper`` / ``rolbypassrls`` false for a restricted role) and the
    table OWNER of each of the five SoR tables (owner keeps privileges even after REVOKE).

Runs in the Decision Service Tests job (superuser ``DATABASE_URL`` + migrations applied). Skipped
when DATABASE_URL is absent so local ``pytest`` without a DB stays green.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import decision_sor_role_certify as csr  # noqa: E402

DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres (DATABASE_URL)")

PLATFORM_PROBE = "cert_platform_probe"
SERVICE_PROBE = "cert_service_probe"
PROBE_PASSWORD = "cert_probe_pw"


async def _admin():
    import asyncpg

    return await asyncpg.connect(DB, statement_cache_size=0)


def _probe_url(role: str) -> str:
    p = urlparse(DB)
    db = (p.path or "/").lstrip("/") or "postgres"
    return f"postgresql://{role}:{PROBE_PASSWORD}@{p.hostname}:{p.port or 5432}/{db}"


async def _drop_probes(admin) -> None:
    for role in (PLATFORM_PROBE, SERVICE_PROBE):
        if await admin.fetchval("SELECT 1 FROM pg_roles WHERE rolname=$1", role):
            await admin.execute(f'DROP ROLE IF EXISTS "{role}"')


async def _create_probes(admin) -> None:
    await _drop_probes(admin)
    for role in (PLATFORM_PROBE, SERVICE_PROBE):
        await admin.execute(
            f"CREATE ROLE \"{role}\" LOGIN PASSWORD '{PROBE_PASSWORD}' "
            "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT"
        )


def test_certification_verdict_is_correct() -> None:
    async def _run():
        admin = await _admin()
        try:
            await _create_probes(admin)
            platform_url = _probe_url(PLATFORM_PROBE)
            service_url = _probe_url(SERVICE_PROBE)

            # 1) Distinct roles → role_separation_confirmed True, correct current_users.
            os.environ["DECISION_SOR_PLATFORM_URL"] = platform_url
            os.environ["DECISION_SOR_SERVICE_URL"] = service_url
            distinct = await csr._run()
            assert distinct["role_separation_confirmed"] is True, distinct
            assert distinct["platform_role"] == PLATFORM_PROBE
            assert distinct["decision_service_role"] == SERVICE_PROBE
            assert distinct["platform"]["current_user"] == PLATFORM_PROBE
            assert distinct["decision_service"]["current_user"] == SERVICE_PROBE

            # Role attributes surfaced + restricted (the whole point of certifying the roles).
            attrs = distinct["platform"]["role_attributes"]
            assert attrs["rolsuper"] is False and attrs["rolbypassrls"] is False, attrs
            # The probe is not a member of any role it could SET ROLE into.
            assert distinct["platform"]["memberships_can_set_role_to"] == []

            # Table owner reported for every SoR table (and it is NOT the probe app role).
            owners = distinct["platform"]["table_owners"]
            assert set(owners) == set(csr.SOR_TABLES)
            for table, owner in owners.items():
                assert owner and owner not in (PLATFORM_PROBE, SERVICE_PROBE), (table, owner)

            # security_definer_writers is enumerated (a list — empty is fine, presence is what matters).
            assert isinstance(distinct["platform"]["security_definer_writers"], list)

            # 2) Same role on both connections → role_separation_confirmed False (do NOT revoke).
            os.environ["DECISION_SOR_SERVICE_URL"] = platform_url
            same = await csr._run()
            assert same["role_separation_confirmed"] is False, same
            assert same["platform_role"] == same["decision_service_role"] == PLATFORM_PROBE
        finally:
            os.environ.pop("DECISION_SOR_PLATFORM_URL", None)
            os.environ.pop("DECISION_SOR_SERVICE_URL", None)
            await _drop_probes(admin)
            await admin.close()

    asyncio.run(_run())
