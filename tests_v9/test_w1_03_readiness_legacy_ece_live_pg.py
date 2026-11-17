"""#1507 review LOW: season readiness and field_state read the same ECe, proved on live PG.

Over HTTP into the platform app, on a migrated Postgres, through a NOBYPASSRLS role:

- ``agree``: an approved v156 EC 1:5 (older) and a *published* legacy ``soil_lab_tests`` ECe
  (newer). field_state reads the legacy ECe (3.0); the season workspace readiness must accept
  it too instead of reporting soil EC missing (it used to skip every legacy candidate, so
  the older 1:5 made the ECe unknown);
- ``unpublished``: the same shape with the newer legacy row only ``approved``. Readiness never
  accepts an approved-not-published legacy row, so it does not count and the older 1:5 still
  leaves the ECe unknown: soil EC missing.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

asyncpg = pytest.importorskip("asyncpg")
httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", DSN)
_TABLES = ("lab_samples", "soil_lab_results", "soil_lab_tests", "fields", "field_state")
_OLD = date.today() - timedelta(days=20)
_NEW = date.today() - timedelta(days=2)


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(ADMIN_DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in _TABLES:
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import api.main as main

    return main


async def _scenario(monkeypatch) -> dict:
    main = _platform()
    from core.canonical_schemas import UserRole, UserSchema

    tenant = str(uuid.uuid4())
    tag = uuid.uuid4().hex[:8]
    fields = {k: f"w103r-{k}-{tag}" for k in ("agree", "unpublished")}
    admin = await asyncpg.connect(ADMIN_DSN)
    role = None
    if (
        await admin.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        and DSN == ADMIN_DSN
    ):
        role = f"w103r_rls_{uuid.uuid4().hex[:10]}"
        await admin.execute(
            f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
            f'GRANT USAGE ON SCHEMA public TO "{role}";'
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}";'
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}";'
            f'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO "{role}";'
        )

    async def setup(conn):
        if role:
            await conn.execute(f'SET ROLE "{role}"')

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4, setup=setup)
    monkeypatch.setattr(main, "_DB_POOL", pool)
    for key, field in fields.items():
        await admin.execute(
            "INSERT INTO fields (field_id, name, tenant_id, lat, lon) "
            "VALUES ($1, $1, $2::uuid, 15.3, 44.2)",
            field,
            tenant,
        )
        # Legacy history written before the freeze: the newer row of each field.
        await admin.execute(
            "INSERT INTO soil_lab_tests (test_id, tenant_id, field_id, status, sampled_on, result)"
            " VALUES ($1, $2::uuid, $3, $4, $5, $6::jsonb)",
            f"soil_{uuid.uuid4().hex[:12]}",
            tenant,
            field,
            "published" if key == "agree" else "approved",
            _NEW,
            '{"ec": 3.0, "ph": 7.4}',
        )
    acting = {"user": None}
    main.app.dependency_overrides[main.get_current_user] = lambda: acting["user"]
    out: dict = {}

    def as_user(actor: str, role_: UserRole = UserRole.MANAGER) -> None:
        acting["user"] = UserSchema(user_id=actor, tenant_id=tenant, role=role_, name_ar="مختبر")

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
            base_url="http://platform",
            timeout=120,
        ) as client:
            for key, field in fields.items():
                # The older v156 analysis: an approved EC 1:5 (not an ECe).
                as_user("lab-tech")
                made = await client.post(
                    "/api/v1/lab/samples",
                    json={
                        "field_id": field,
                        "kind": "soil",
                        "latitude": 15.3,
                        "longitude": 44.2,
                        "depth_cm_from": 0,
                        "depth_cm_to": 30,
                        "sampled_on": _OLD.isoformat(),
                    },
                )
                assert made.status_code == 200, made.text
                sid = made.json()["sample_id"]
                put = await client.post(
                    "/api/v1/lab/soil-results",
                    json={
                        "sample_id": sid,
                        "ec_dsm": 0.4,
                        "ec_extraction_method": "soil_water_1_5",
                    },
                )
                assert put.status_code == 200, put.text
                as_user("reviewer", UserRole.AGRONOMIST)
                ok = await client.post(
                    f"/api/v1/lab/samples/{sid}/transition", json={"target_status": "approved"}
                )
                assert ok.status_code == 200, ok.text
                as_user("viewer")
                out[f"{key}_state"] = (await client.get(f"/api/v1/fields/{field}/state")).json()
                workspace = await client.get(f"/api/v1/fields/{field}/season-workspace")
                assert workspace.status_code == 200, workspace.text
                out[f"{key}_workspace"] = workspace.json()
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        await pool.close()
        await admin.close()
    return out


@pytest.fixture(scope="module")
def scenario():
    mp = pytest.MonkeyPatch()
    try:
        yield asyncio.run(_scenario(mp))
    finally:
        mp.undo()


def _soil_ec_ok(workspace: dict) -> bool:
    checks = {c["key"]: c["ok"] for c in workspace["readiness"]["checks"]}
    assert "soil_ec" in checks, f"readiness must score soil EC: {checks}"
    return checks["soil_ec"]


def test_readiness_accepts_the_published_legacy_ece_field_state_reads(scenario):
    soil = scenario["agree_state"]["soil_lab"]
    assert soil["ec_dsm"] == 3.0, f"field_state reads the newer published legacy ECe: {soil}"
    assert _soil_ec_ok(scenario["agree_workspace"]) is True, (
        "readiness reported soil EC missing while field_state has the published legacy ECe"
    )


def test_readiness_never_accepts_an_unpublished_legacy_ece(scenario):
    assert _soil_ec_ok(scenario["unpublished_workspace"]) is False, (
        "an approved-not-published legacy row must not satisfy readiness soil EC"
    )
