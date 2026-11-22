"""W0-07 (finding scout-1): an edge result is written under the tenant it was taken for (live PG).

Before: every edge result went to ``/v1/edge/sync`` under one ``EDGE_SYNC_TOKEN`` bearer, so all
of them were written under that token's tenant. A detection for a field of tenant B was refused
(404 ⇒ dead-letter), and a stream that named a field of the token's tenant wrote into it.

Now each envelope carries the tenant its caller signed for, and the edge sends it in service
mode (agent token + tenant assertion). This file drives the real edge ``CloudSyncService`` over
HTTP into the real platform route, against a migrated Postgres through a NOBYPASSRLS role:

* tenant B's detection on B's field is stored under B (and A sees nothing);
* tenant A's envelope naming B's field is refused (404 ⇒ dead-letter), nothing is stored;
* a request whose assertion names another tenant than its header is 403 and stores nothing;
* a replay with the same idempotency key is ``duplicate_ignored`` only when its JSON is the same
  ``jsonb``: turning ``"reviewed": true`` into ``1`` is ``409`` and the stored row keeps ``true``
  (Edge v286 lab finding, fixed in #1569; the unit file only proves the comparator).
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

# Switch read before any import (test_certification_switch_precedes_importorskip): on the
# certifying CI step a missing dependency or an unusable database fails the run, not a skip.
_CERTIFICATION_REQUIRED = os.getenv("EDGE_SYNC_TENANT_CERTIFICATION_REQUIRED") == "1"


def _require(module: str):
    """Import ``module``; under the certification switch a missing one fails the run."""
    if _CERTIFICATION_REQUIRED:
        return importlib.import_module(module)
    return pytest.importorskip(module)


asyncpg = _require("asyncpg")
httpx = _require("httpx")
_require("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv("TEST_DATABASE_URL", "")
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", "")
TOKEN = "live-edge-agent-token-value"
KEY = "live-edge-tenant-assertion-key-0123456789"

if _CERTIFICATION_REQUIRED and not (DSN and ADMIN_DSN):
    raise RuntimeError(
        "EDGE_SYNC_TENANT_CERTIFICATION_REQUIRED=1 needs TEST_DATABASE_URL and TEST_DATABASE_ADMIN_URL"
    )

pytestmark.append(
    pytest.mark.skipif(
        not (DSN and ADMIN_DSN),
        reason="declared skip (not a pass): needs TEST_DATABASE_URL and TEST_DATABASE_ADMIN_URL",
    )
)


def _sync_module():
    name = "edge_sync_service_live_w0_07"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "services/edge-inference/sync_service.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None, spec
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _observation(field_id: str) -> dict:
    return {
        "field_id": field_id,
        "device_id": "edge-live-w0-07",
        "timestamp": "2026-11-16T08:00:00+00:00",
        "detections": [{"class_name": "aphid", "confidence": 0.9}],
    }


async def _run(monkeypatch, tmp_path) -> dict:
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.setenv("EDGE_SYNC_TENANT_ASSERTION_KEY", KEY)
    monkeypatch.delenv("EDGE_SYNC_ALLOWED_CALLERS", raising=False)
    monkeypatch.delenv("PLATFORM_TENANT_ASSERTION_REDIS_URL", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.setattr(main, "_RATE_LIMIT_PER_MIN", 0, raising=False)

    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    tag = f"w007-{uuid.uuid4().hex[:8]}"
    field_a, field_b = f"{tag}-a", f"{tag}-b"
    admin = await asyncpg.connect(ADMIN_DSN)
    for field, tenant in ((field_a, tenant_a), (field_b, tenant_b)):
        # The route checks ownership in `fields`; edge_results.field_id still references
        # field_boundaries (pre-existing, outside W0-07), so the field is seeded in both.
        await admin.execute(
            "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, $1, $2::uuid)",
            field,
            tenant,
        )
        await admin.execute(
            "INSERT INTO field_boundaries (field_id, field_name, tenant_id) "
            "VALUES ($1, $1, $2::uuid)",
            field,
            tenant,
        )
    app_conn = await asyncpg.connect(DSN)
    restricted = await app_conn.fetchval(
        "SELECT NOT (rolsuper OR rolbypassrls) FROM pg_roles WHERE rolname = current_user"
    )
    await app_conn.close()
    assert restricted, "TEST_DATABASE_URL must be a NOBYPASSRLS role, or isolation is not measured"
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    monkeypatch.setattr(main, "_DB_POOL", pool)

    sync_mod = _sync_module()
    real_client = httpx.AsyncClient
    transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
    monkeypatch.setattr(
        sync_mod.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=transport, **{k: v for k, v in kw.items()}),
    )
    edge = sync_mod.CloudSyncService(
        "http://platform",
        "",  # no bearer at all: service mode only
        str(tmp_path / "queue"),
        agent_token=TOKEN,
        assertion_key=KEY,
    )
    out: dict = {}
    try:
        out["b_on_b"] = await edge.sync_result(
            "pest_detection", _observation(field_b), tenant_id=tenant_b
        )
        out["a_on_b"] = await edge.sync_result(
            "pest_detection", _observation(field_b), tenant_id=tenant_a
        )
        out["dead_letter"] = edge.dead_letter_size()

        # Header says B, assertion says A: refused before any write.
        item = edge._envelope("pest_detection", _observation(field_b), tenant_id=tenant_a)
        headers = edge._headers(item)
        headers["X-Tenant-Id"] = tenant_b
        async with real_client(transport=transport, base_url="http://platform") as client:
            swapped = await client.post("/v1/edge/sync", json=item, headers=headers)
        out["swapped"] = swapped.status_code

        rows = await admin.fetch(
            "SELECT tenant_id::text AS tenant_id, field_id FROM edge_results WHERE field_id LIKE $1",
            f"{tag}-%",
        )
        out["rows"] = [dict(r) for r in rows]
        scoped = await asyncpg.connect(DSN)
        try:
            async with scoped.transaction():
                await scoped.execute("SELECT set_config('app.current_tenant', $1, true)", tenant_a)
                out["a_sees"] = await scoped.fetchval(
                    "SELECT count(*) FROM edge_results WHERE field_id LIKE $1", f"{tag}-%"
                )
        finally:
            await scoped.close()
    finally:
        await pool.close()
        await admin.execute("DELETE FROM edge_results WHERE field_id LIKE $1", f"{tag}-%")
        await admin.execute("DELETE FROM fields WHERE field_id LIKE $1", f"{tag}-%")
        await admin.execute("DELETE FROM field_boundaries WHERE field_id LIKE $1", f"{tag}-%")
        await admin.close()
    out["tenants"] = (tenant_a, tenant_b, field_b)
    return out


def test_each_edge_result_is_written_under_the_tenant_it_was_taken_for(monkeypatch, tmp_path):
    out = asyncio.run(_run(monkeypatch, tmp_path))
    tenant_a, tenant_b, field_b = out["tenants"]
    assert out["b_on_b"] is True, out
    assert out["rows"] == [{"tenant_id": tenant_b, "field_id": field_b}], (
        "tenant B's detection must be stored under B, and nothing else stored",
        json.dumps(out, default=str),
    )
    assert out["a_on_b"] is False, "A's envelope on B's field must not be accepted"
    assert out["dead_letter"] == 1, "the cross-tenant envelope is a permanent rejection (404)"
    assert out["swapped"] == 403, out["swapped"]
    assert out["a_sees"] == 0, "RLS: tenant A must not see B's result"


async def _run_replay(monkeypatch, tmp_path) -> dict:
    """One envelope sent three times under one idempotency key: as stored, identical, true → 1."""
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.setenv("EDGE_SYNC_TENANT_ASSERTION_KEY", KEY)
    monkeypatch.delenv("EDGE_SYNC_ALLOWED_CALLERS", raising=False)
    monkeypatch.delenv("PLATFORM_TENANT_ASSERTION_REDIS_URL", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.setattr(main, "_RATE_LIMIT_PER_MIN", 0, raising=False)

    tenant = str(uuid.uuid4())
    tag = f"replay-{uuid.uuid4().hex[:8]}"
    field = f"{tag}-f"
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(
        "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, $1, $2::uuid)", field, tenant
    )
    await admin.execute(
        "INSERT INTO field_boundaries (field_id, field_name, tenant_id) VALUES ($1, $1, $2::uuid)",
        field,
        tenant,
    )
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
    monkeypatch.setattr(main, "_DB_POOL", pool)
    sync_mod = _sync_module()
    edge = sync_mod.CloudSyncService(
        "http://platform",
        "",
        str(tmp_path / "queue"),
        agent_token=TOKEN,
        assertion_key=KEY,
    )
    transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
    key = uuid.uuid4().hex
    out: dict = {}
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://platform") as client:

            async def send(reviewed) -> tuple[int, dict]:
                data = {**_observation(field), "reviewed": reviewed}
                item = edge._envelope("pest_detection", data, key, tenant_id=tenant)
                # Fresh signed headers per request; the assertion signs method, path and tenant.
                response = await client.post(
                    "/v1/edge/sync", json=item, headers=edge._headers(item)
                )
                return response.status_code, response.json()

            out["first"] = await send(True)
            out["identical"] = await send(True)
            out["true_to_1"] = await send(1)
        rows = await admin.fetch(
            "SELECT result_data->'reviewed' AS reviewed FROM edge_results "
            "WHERE tenant_id = $1::uuid AND idempotency_key = $2",
            tenant,
            key,
        )
        out["stored"] = [r["reviewed"] for r in rows]
    finally:
        await pool.close()
        await admin.execute("DELETE FROM edge_results WHERE field_id = $1", field)
        await admin.execute("DELETE FROM fields WHERE field_id = $1", field)
        await admin.execute("DELETE FROM field_boundaries WHERE field_id = $1", field)
        await admin.close()
    return out


def test_a_replay_that_turns_true_into_1_is_a_conflict_and_the_row_keeps_true(
    monkeypatch, tmp_path
):
    out = asyncio.run(_run_replay(monkeypatch, tmp_path))
    first_status, first = out["first"]
    assert first_status == 200 and first.get("status") == "stored", out
    identical_status, identical = out["identical"]
    assert identical_status == 200 and identical.get("status") == "duplicate_ignored", out
    assert identical.get("id") == first.get("id"), out
    status, body = out["true_to_1"]
    assert status == 409, (
        "true -> 1 under the same key must be a conflict, not a duplicate receipt",
        json.dumps(out, default=str),
    )
    assert body.get("detail") == "edge_idempotency_conflict", out
    assert out["stored"] == ["true"], ("exactly one row, still holding true", out["stored"])
