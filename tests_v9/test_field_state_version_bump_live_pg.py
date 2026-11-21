"""field_state.version is bumped by every recompute write (exploration bug; v132 column).

v132 added ``field_state.version`` as "a monotonic per-field recompute counter", but the only
writer (``recompute_field_state``) never touched it: every row stayed at 1, so a stale recompute
could not be told from a newer one. The fix bumps the version inside the UPSERT statement itself
and adds an optional ``expected_version`` for a conditional (optimistic-concurrency) write.

Live PostgreSQL through the restricted role (NOBYPASSRLS, FORCE RLS on field_state): the bump
is SQL, so a fake connection could not show it. Without the fix the version stays at 1 after
two recomputes (negative control recorded in the commit).

The CI integration step sets ``FIELD_STATE_VERSION_CERTIFICATION_REQUIRED=1``, so an unreachable
or unmigrated database fails the module instead of turning the proof into a green skip.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

# Switch read before any import: on a certifying runner a missing dependency must fail the
# module, not importorskip it into a green skip (certification-switch-before-importorskip).
_REQUIRED = os.getenv("FIELD_STATE_VERSION_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
except ImportError:
    if _REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", DSN)


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        has_version = await conn.fetchval(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'field_state' AND column_name = 'version'"
        )
        if not has_version:
            return "schema not migrated (field_state.version missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())


@pytest.fixture(autouse=True)
def _database_or_declared_skip():
    if _WHY:
        message = f"field_state.version live certification has no database: {_WHY}"
        if _REQUIRED:
            pytest.fail(message, pytrace=False)
        pytest.skip(f"declared skip (not a pass): {message}")


def _projection():
    for path in (str(PLATFORM), str(ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)
    from api import field_state_projection

    return field_state_projection


async def _new_field() -> tuple[str, str]:
    tenant, field = str(uuid.uuid4()), f"fsv-{uuid.uuid4().hex[:10]}"
    conn = await asyncpg.connect(DSN)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            await conn.execute(
                "INSERT INTO fields (field_id, tenant_id, name) VALUES ($1, $2::uuid, $3)",
                field,
                tenant,
                "version bump field",
            )
    finally:
        await conn.close()
    return tenant, field


async def _recompute(tenant: str, field: str, **kwargs) -> dict:
    proj = _projection()
    conn = await asyncpg.connect(DSN)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            return await proj.recompute_field_state(conn, field, **kwargs)
    finally:
        await conn.close()


async def _recomputed_at(tenant: str, field: str):
    conn = await asyncpg.connect(DSN)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            return await conn.fetchval(
                "SELECT recomputed_at FROM field_state WHERE field_id = $1", field
            )
    finally:
        await conn.close()


async def _version(tenant: str, field: str) -> int | None:
    conn = await asyncpg.connect(DSN)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            return await conn.fetchval("SELECT version FROM field_state WHERE field_id = $1", field)
    finally:
        await conn.close()


def test_two_recomputes_leave_version_plus_two():
    async def scenario():
        tenant, field = await _new_field()
        await _recompute(tenant, field)
        first = await _version(tenant, field)
        await _recompute(tenant, field)
        await _recompute(tenant, field)
        return first, await _version(tenant, field)

    first, after = asyncio.run(scenario())
    assert first == 1, f"a new field_state row starts at version 1, got {first}"
    assert after == first + 2, f"two more recomputes must leave version+2 ({first}+2), got {after}"


def test_concurrent_recomputes_each_bump_the_version():
    async def scenario():
        tenant, field = await _new_field()
        await _recompute(tenant, field)
        await asyncio.gather(*(_recompute(tenant, field) for _ in range(4)))
        return await _version(tenant, field)

    after = asyncio.run(scenario())
    assert after == 5, f"1 + 4 concurrent recomputes must give version 5, no lost bump: {after}"


def test_expected_version_write_applies_once_and_refuses_the_stale_writer():
    proj = _projection()

    async def scenario():
        tenant, field = await _new_field()
        created = await _recompute(tenant, field, expected_version=0)
        bumped = await _recompute(tenant, field, expected_version=1)
        with pytest.raises(proj.FieldStateVersionConflict) as stale:
            await _recompute(tenant, field, expected_version=1)
        with pytest.raises(proj.FieldStateVersionConflict):
            await _recompute(tenant, field, expected_version=0)
        return created, bumped, stale.value, await _version(tenant, field)

    created, bumped, stale, stored = asyncio.run(scenario())
    assert created["version"] == 1, f"create-only write must report version 1: {created}"
    assert bumped["version"] == 2, f"matching expected_version must report version 2: {bumped}"
    assert stale.expected_version == 1, f"the conflict must name the stale version: {stale}"
    assert stored == 2, f"refused stale writes must leave the stored version at 2, got {stored}"


def test_expected_version_for_a_missing_row_is_refused():
    proj = _projection()

    async def scenario():
        tenant, field = await _new_field()
        with pytest.raises(proj.FieldStateVersionConflict):
            await _recompute(tenant, field, expected_version=3)
        return await _version(tenant, field)

    assert asyncio.run(scenario()) is None, "a refused write must not create the row"


def test_expected_version_must_be_a_non_negative_integer():
    async def scenario():
        tenant, field = await _new_field()
        for bad in (-1, True, "2"):
            with pytest.raises(ValueError):
                await _recompute(tenant, field, expected_version=bad)
        return await _version(tenant, field)

    assert asyncio.run(scenario()) is None, "an invalid expected_version must write nothing"


def test_first_recompute_stamps_recomputed_at():
    async def scenario():
        tenant, field = await _new_field()
        await _recompute(tenant, field)
        first = await _recomputed_at(tenant, field)
        await _recompute(tenant, field)
        return first, await _recomputed_at(tenant, field)

    first, second = asyncio.run(scenario())
    assert first is not None, "the INSERT path must stamp recomputed_at on a new field_state row"
    assert second is not None and second >= first, (
        f"a later recompute must keep recomputed_at set and not move it back: {first} -> {second}"
    )
