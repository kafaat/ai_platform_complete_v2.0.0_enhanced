"""W0-05 (findings fields-5 / routes-5): the asserted tenant is the tenant RLS scopes to (live PG).

The unit file (test_internal_tenant_assertion_w0_05.py) proves every refusal happens before
the database. This file proves the positive side on a migrated Postgres through a NOBYPASSRLS
role, with no stand-in connection: a request that passes the tenant assertion runs under
exactly the asserted tenant, so

* tenant B, signed for B, reads B's field state;
* tenant A, signed for A, naming B's field gets 404 on both internal routes (RLS hides it);
* a valid assertion for A presented with ``tenant_id=B`` is 403 before any read.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

# Switch read before any import (test_certification_switch_precedes_importorskip): on the
# certifying CI step a missing dependency or an unusable database fails the run, not a skip.
_CERTIFICATION_REQUIRED = os.getenv("INTERNAL_TENANT_ASSERTION_CERTIFICATION_REQUIRED") == "1"


def _require(module: str):
    """Import ``module``; under the certification switch a missing one fails the run."""
    if _CERTIFICATION_REQUIRED:
        return importlib.import_module(module)
    return pytest.importorskip(module)


asyncpg = _require("asyncpg")
httpx = _require("httpx")
_require("fastapi")

from shared.security.tenant_assertion_headers import tenant_assertion_headers  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv("TEST_DATABASE_URL", "")
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", "")
TOKEN = "live-internal-agent-token-value"
KEY = "live-w0-05-platform-assertion-key-0123456789"
ADVICE_PATH = "/internal/events/ai-advice"

if _CERTIFICATION_REQUIRED and not (DSN and ADMIN_DSN):
    raise RuntimeError(
        "INTERNAL_TENANT_ASSERTION_CERTIFICATION_REQUIRED=1 needs TEST_DATABASE_URL and TEST_DATABASE_ADMIN_URL"
    )

pytestmark.append(
    pytest.mark.skipif(
        not (DSN and ADMIN_DSN),
        reason="declared skip (not a pass): needs TEST_DATABASE_URL and TEST_DATABASE_ADMIN_URL",
    )
)


def _signed(tenant: str, method: str, path: str, service: str) -> dict[str, str]:
    return {
        "X-Agent-Token": TOKEN,
        **tenant_assertion_headers(
            key=KEY, key_id="current", service=service, tenant_id=tenant, method=method, path=path
        ),
    }


async def _run(monkeypatch) -> dict:
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.setenv("PLATFORM_TENANT_ASSERTION_KEY", KEY)
    monkeypatch.delenv("PLATFORM_INTERNAL_ALLOWED_CALLERS", raising=False)
    monkeypatch.delenv("PLATFORM_TENANT_ASSERTION_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.setattr(main, "_RATE_LIMIT_PER_MIN", 0, raising=False)

    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    field_b = f"w005-{uuid.uuid4().hex[:8]}-b"
    state_path = f"/internal/fields/{field_b}/state"
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(
        "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, $1, $2::uuid)",
        field_b,
        tenant_b,
    )
    app_conn = await asyncpg.connect(DSN)
    restricted = await app_conn.fetchval(
        "SELECT NOT (rolsuper OR rolbypassrls) FROM pg_roles WHERE rolname = current_user"
    )
    await app_conn.close()
    assert restricted, "TEST_DATABASE_URL must be a NOBYPASSRLS role, or isolation is not measured"
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    monkeypatch.setattr(main, "_DB_POOL", pool)

    out: dict = {"field_b": field_b}
    transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://platform") as client:
            r = await client.get(
                state_path,
                params={"tenant_id": tenant_b},
                headers=_signed(tenant_b, "GET", state_path, "supervisor-agent"),
            )
            out["b_on_b"] = (r.status_code, r.text[:300])
            r = await client.get(
                state_path,
                params={"tenant_id": tenant_a},
                headers=_signed(tenant_a, "GET", state_path, "supervisor-agent"),
            )
            out["a_on_b_state"] = (r.status_code, r.text[:300])
            r = await client.get(
                state_path,
                params={"tenant_id": tenant_b},
                headers=_signed(tenant_a, "GET", state_path, "supervisor-agent"),
            )
            out["a_claims_b"] = (r.status_code, r.text[:300])
            body = {"tenant_id": tenant_a, "field_id": field_b, "question": "q"}
            r = await client.post(
                ADVICE_PATH,
                json=body,
                headers=_signed(tenant_a, "POST", ADVICE_PATH, "ai_agronomist"),
            )
            out["a_on_b_advice"] = (r.status_code, r.text[:300])
    finally:
        await pool.close()
        await admin.execute("DELETE FROM fields WHERE field_id = $1", field_b)
        await admin.close()
    return out


def test_the_asserted_tenant_is_the_tenant_rls_scopes_to(monkeypatch):
    out = asyncio.run(_run(monkeypatch))
    assert out["b_on_b"][0] == 200, f"B signed for B must read B's field state: {out}"
    assert out["field_b"] in out["b_on_b"][1], f"B's state must name B's field: {out}"
    assert out["a_on_b_state"][0] == 404, f"A signed for A must not see B's field: {out}"
    assert out["a_claims_b"][0] == 403, f"an assertion for A must not open tenant B: {out}"
    assert out["a_on_b_advice"][0] == 404, f"A's advice must not attach to B's field: {out}"
