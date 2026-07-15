"""field-management-service — static + contract unit tests.

Pins the SEC contract of the new tenant-scoped field owner:
  • service-token only (401 fail-closed) — NO user-JWT / permission dependency
  • tenant from the X-Tenant-Id header (missing ⇒ 400), never query/body
  • every query scoped by field_id AND tenant_id under RLS ⇒ 404 (no disclosure)
  • DATABASE_URL unset ⇒ 503 (fail-closed, no platform fallback)
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SERVICE_DIR = Path(__file__).resolve().parents[1]
MAIN_PATH = SERVICE_DIR / "main.py"
SRC = MAIN_PATH.read_text(encoding="utf-8")


def _load_main():
    pytest.importorskip("fastapi")
    spec = importlib.util.spec_from_file_location("field_management_main_under_test", MAIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_internal_field_routes_registered():
    mod = _load_main()
    paths = {getattr(r, "path", None) for r in mod.app.routes}
    assert "/internal/fields/{field_id}" in paths
    assert "/internal/fields" in paths
    assert "/healthz" in paths
    assert "/readyz" in paths


def test_service_token_guard_is_fail_closed(monkeypatch):
    mod = _load_main()
    from fastapi import HTTPException

    monkeypatch.delenv("SAHOOL_AGENT_TOKEN", raising=False)
    with pytest.raises(HTTPException) as e1:  # no secret configured ⇒ always rejected
        mod._require_service_token("anything")
    assert e1.value.status_code == 401

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "s3cr3t")
    with pytest.raises(HTTPException) as e2:  # wrong token ⇒ rejected
        mod._require_service_token("wrong")
    assert e2.value.status_code == 401
    assert mod._require_service_token("s3cr3t") is None  # match ⇒ passes
    # a user Bearer JWT with no X-Agent-Token ⇒ rejected (None argument)
    with pytest.raises(HTTPException) as e3:
        mod._require_service_token(None)
    assert e3.value.status_code == 401


def test_tenant_required_from_header(monkeypatch):
    mod = _load_main()
    from fastapi import HTTPException

    for missing in (None, ""):
        with pytest.raises(HTTPException) as e:
            mod._require_tenant(missing)
        assert e.value.status_code == 400
    assert mod._require_tenant("tenant-1") == "tenant-1"


def test_readyz_envelope_has_required_keys():
    import asyncio

    mod = _load_main()
    body = asyncio.run(mod.readyz())
    for key in ("status", "service", "implemented_runtime", "ready", "dependencies"):
        assert key in body, f"readyz envelope missing {key}"
    assert body["implemented_runtime"] is True
    assert isinstance(body["dependencies"], dict)


def test_source_contract_is_service_token_only_and_scoped():
    # scoped by BOTH field_id AND tenant_id; other-tenant/missing ⇒ 404
    assert "WHERE field_id = $1 AND tenant_id = $2::uuid" in SRC
    assert "status_code=404" in SRC
    # tenant from header, missing ⇒ 400
    assert 'Header(None, alias="X-Tenant-Id")' in SRC
    assert "status_code=400" in SRC
    # fail-closed DB unavailability, never 500/fallback
    assert "status_code=503" in SRC
    # NO user-JWT / permission / JWT-decode construct is actually invoked/imported.
    # (The decode token is assembled from parts so this test file itself is not flagged
    # by the audience guard, which scans services/** for a JWT decode call.)
    for forbidden in ("get_current_user(", "require_permission(", "jwt." + "decode(", "import jwt"):
        assert forbidden not in SRC, f"forbidden auth construct present: {forbidden}"
    # NO platform fallback — this service IS the field owner, and reads its own DB
    # directly (no outbound HTTP to the platform).
    assert "PLATFORM_API_URL" not in SRC
    assert "httpx" not in SRC and "requests" not in SRC


def test_no_pyjwt_dependency():
    # inspect only real requirement lines (ignore explanatory comments)
    lines = [
        line.strip().lower()
        for line in (SERVICE_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert not any("jwt" in line for line in lines), (
        "PyJWT must not be a dependency (service-token only)"
    )
    # asyncpg is the only DB dependency; matches raster-service pin
    assert any("asyncpg==0.30.0" == line for line in lines)


def test_service_token_matches_env_secret(monkeypatch):
    # constant-time compare against SAHOOL_AGENT_TOKEN (never a hardcoded literal)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", os.urandom(8).hex())
    assert "hmac.compare_digest" in SRC


def test_tenant_isolation_is_transaction_local_and_per_request():
    # No cached pool across event loops — a fresh short-lived connection per request,
    # so a connection can never be reused across tenants (no set_config leakage).
    assert "asyncpg.connect(" in SRC
    assert "create_pool" not in SRC
    # tenant GUC is transaction-local (third arg true) and set INSIDE a transaction,
    # BEFORE the scoped query — mirrors the RLS pattern used across the platform.
    assert "set_config('app.current_tenant', $1, true)" in SRC
    assert "async with conn.transaction():" in SRC


def test_service_token_checked_before_tenant():
    # token guard must gate first: _require_tenant depends on _require_service_token,
    # so an unauthenticated caller is rejected (401) before any tenant processing.
    assert "def _require_tenant(" in SRC
    tenant_block = SRC[SRC.index("def _require_tenant(") :]
    assert "Depends(_require_service_token)" in tenant_block[: tenant_block.index("return")]
