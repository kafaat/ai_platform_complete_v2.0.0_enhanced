"""The dispatch device gate reads the registered field from iot_devices (live PG).

The field kill switch must hold a command that names no field by the field its valve is
installed in, so ``_validate_dispatch_device`` returns the device's registered field. This was
a unit test on a connection stand-in that returned the row the test wrote; here the function
reads iot_devices through a NOBYPASSRLS role on a migrated Postgres, under the tenant set in
its own transaction:

- no field named: accepted, and the registered field is reported;
- another field named: device_field_mismatch, registered field still reported;
- another tenant's device: device_not_found under RLS, no field disclosed.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

asyncpg = pytest.importorskip("asyncpg")

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "services" / "actuator-service" / "actuator_runtime.py"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in ("iot_devices", "fields"):
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _runtime():
    # The same loading as services/actuator-service/test_dispatch_bridge.py: aiomqtt may be
    # absent, and the underscore helpers live in actuator_runtime.py.
    if "aiomqtt" not in sys.modules:
        try:
            import aiomqtt  # noqa: F401
        except ImportError:
            stub = types.ModuleType("aiomqtt")
            stub.Client = object
            sys.modules["aiomqtt"] = stub
    os.environ.setdefault("ACTUATOR_DEDUP_WINDOW_SEC", "60")
    spec = importlib.util.spec_from_file_location("actuator_runtime_registry_live", RUNTIME)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _measure(runtime) -> dict:
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    tag = uuid.uuid4().hex[:8]
    field, device = f"dr-field-{tag}", f"dr-valve-{tag}"
    owner = await asyncpg.connect(DSN)
    role = None
    if await owner.fetchval(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ):
        role = f"dr_rls_{uuid.uuid4().hex[:10]}"
        await owner.execute(
            f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
            f'GRANT USAGE ON SCHEMA public TO "{role}";'
            f'GRANT SELECT ON iot_devices TO "{role}";'
        )

    async def setup(conn):
        if role:
            await conn.execute(f'SET ROLE "{role}"')

    try:
        await owner.execute(
            "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, $1, $2::uuid)",
            field,
            tenant,
        )
        await owner.execute(
            """INSERT INTO iot_devices (device_id, tenant_id, name, type, field_id, status,
                                        last_seen_at)
               VALUES ($1, $2::uuid, 'valve', 'actuator', $3, 'online', $4)""",
            device,
            tenant,
            field,
            datetime.now(UTC),
        )
        runtime._pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2, setup=setup)
        try:
            return {
                "unnamed": await runtime._validate_dispatch_device(tenant, device, None),
                "other_field": await runtime._validate_dispatch_device(tenant, device, "east"),
                "other_tenant": await runtime._validate_dispatch_device(other, device, None),
                "field": field,
            }
        finally:
            await runtime._pool.close()
            runtime._pool = None
    finally:
        await owner.execute("DELETE FROM iot_devices WHERE device_id = $1", device)
        await owner.execute("DELETE FROM fields WHERE field_id = $1", field)
        if role:
            await owner.execute(f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')
        await owner.close()


@pytest.fixture(scope="module")
def measured():
    return asyncio.run(_measure(_runtime()))


def test_a_command_without_a_field_gets_the_device_s_registered_field(measured):
    assert measured["unnamed"] == (True, "ok", measured["field"])


def test_a_command_for_another_field_is_refused_with_the_registered_field(measured):
    assert measured["other_field"] == (False, "device_field_mismatch", measured["field"])


def test_another_tenant_does_not_see_the_device(measured):
    assert measured["other_tenant"] == (False, "device_not_found", None)
