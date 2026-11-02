"""S5 (MCP) — the MCP servers honour auth's JWT revocation (audit 2026-11-01).

**Fault on origin/main cc0d2e295 (and on the S5 branch):** every MCP server authenticates through
``services/mcp_servers/shared/oauth_middleware.py`` ``_authenticate_token`` (``require_scope`` and
``MCPPreAuthMiddleware``), and market's REST routes through ``market_server.verify_token``. Both
decoded the token and checked issuer/scope/tenant, nothing else: a token auth revoked on logout
(``jti``) or by revoke-all-sessions on a role/password change (per-user ``token_floor``) kept
working on all five servers until it expired.

**Fix:** ``_authenticate_token`` ends with ``require_not_revoked`` (``shared/security/
token_revocation.py``, the platform's rule and policy: fail-open per check, production refuses to
start without the store); market's ``_get_current_user`` calls the same helper.

A fake store per case: revoked jti ⇒ 401 · issued before the floor ⇒ 401 · valid ⇒ accepted —
on an MCP route of each server and on a market REST route.
"""

from __future__ import annotations

import importlib.util
import sys
import time
import uuid
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "services/mcp_servers"
SECRET = "s5-mcp-revocation-test-secret-0123456789-abcdefgh"
TENANT = "tenant-a"


class FakeStore:
    """Fake revocation store: the two reads auth's keys answer."""

    def __init__(self, revoked=(), floors=None):
        self.revoked = set(revoked)
        self.floors = dict(floors or {})

    def is_revoked(self, jti):
        return jti in self.revoked

    def token_floor(self, sub):
        return self.floors.get(str(sub))


class BrokenStore:
    def is_revoked(self, jti):
        raise ConnectionError("redis down")

    def token_floor(self, sub):
        raise ConnectionError("redis down")


def _token(scope: str) -> tuple[str, dict]:
    now = int(time.time())
    claims = {
        "sub": "42",
        "tenant_id": TENANT,
        "scope": scope,
        "role": "farmer",
        "iss": "sahool-auth",
        "aud": "sahool",
        "iat": now - 60,
        "exp": now + 600,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, SECRET, algorithm="HS256"), claims


def _store(case: str, claims: dict):
    return {
        "revoked_jti": FakeStore(revoked={claims["jti"]}),
        "issued_before_floor": FakeStore(floors={"42": claims["iat"] + 1}),
        "valid": FakeStore(revoked={"other-jti"}, floors={"42": claims["iat"]}),
        "store_down": BrokenStore(),
    }[case]


REJECTED = {"revoked_jti", "issued_before_floor"}
CASES = ("revoked_jti", "issued_before_floor", "valid", "store_down")


def _exec(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mcp(monkeypatch):
    """Fresh oauth module + loader for the real MCP apps bound to it (no cached instance)."""
    import shared

    monkeypatch.setattr(shared, "__path__", [str(ROOT / "shared"), str(MCP / "shared")])
    monkeypatch.syspath_prepend(str(MCP))
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.setenv("MCP_SERVICE", "field")
    for var in (
        "JWT_PUBLIC_KEY",
        "SAHOOL_ALLOW_HS256_IN_PROD",
        "SAHOOL_ACCESS_TOKEN_CLAIM_POLICY",
        "DENYLIST_REDIS_URL",
        "REDIS_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    loaded: list[str] = []
    oauth = _exec("_s5_mcp_oauth", MCP / "shared/oauth_middleware.py")
    loaded.append("_s5_mcp_oauth")
    monkeypatch.setitem(sys.modules, "shared.oauth_middleware", oauth)
    assert (
        getattr(oauth, "_REVOCATION", None) is None
    )  # no Redis outside production ⇒ check off until patched

    def load(module_name: str):
        name = "_s5_mcp_" + module_name
        loaded.append(name)
        return _exec(name, MCP / (module_name + ".py"))

    yield oauth, load
    for name in loaded:
        sys.modules.pop(name, None)


SERVERS = [
    ("sentinel_hub_server", "satellite:read"),
    ("weather_server", "weather:read"),
    ("wofost_server", "crop:read"),
    ("market_server", "market:read"),
    ("generic_context_server", "mcp:context:read"),
]


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("module_name,scope", SERVERS, ids=[s for s, _ in SERVERS])
def test_mcp_tools_route_honours_revocation(mcp, monkeypatch, module_name, scope, case):
    oauth, load = mcp
    app = load(module_name).app
    token, claims = _token(scope)
    monkeypatch.setattr(oauth, "_REVOCATION", _store(case, claims), raising=False)
    response = TestClient(app).get("/v1/mcp/tools", headers={"Authorization": "Bearer " + token})
    if case in REJECTED:
        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Token revoked"
    else:
        assert response.status_code == 200, response.text


@pytest.mark.parametrize("case", CASES)
def test_mcp_pre_body_middleware_honours_revocation(mcp, monkeypatch, case):
    """``MCPPreAuthMiddleware`` (before the body is read) rejects a revoked token too."""
    oauth, load = mcp
    app = load("generic_context_server").app
    token, claims = _token("mcp:context:read")
    monkeypatch.setattr(oauth, "_REVOCATION", _store(case, claims), raising=False)
    response = TestClient(app).post(
        "/v1/mcp/tools/call",
        content=b'{"name":',
        headers={"Authorization": "Bearer " + token, "content-type": "application/json"},
    )
    if case in REJECTED:
        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Token revoked"
    else:
        assert response.status_code != 401, response.text


@pytest.mark.parametrize("case", CASES)
def test_market_rest_route_honours_revocation(mcp, monkeypatch, case):
    """Market's REST routes authenticate through ``verify_token``, not ``_authenticate_token``."""
    oauth, load = mcp
    market = load("market_server")
    seen = []

    async def get_supplier(args):
        seen.append(args)
        return {"supplier_id": args["supplier_id"]}

    monkeypatch.setattr(market, "tool_get_supplier", get_supplier)
    token, claims = _token("market:read")
    monkeypatch.setattr(oauth, "_REVOCATION", _store(case, claims), raising=False)
    response = TestClient(market.app).get(
        "/v1/suppliers/s-1", headers={"Authorization": "Bearer " + token}
    )
    if case in REJECTED:
        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Token revoked"
        assert seen == []
    else:
        assert response.status_code == 200, response.text
        assert seen == [{"supplier_id": "s-1", "tenant_id": TENANT}]


def test_production_refuses_to_import_the_mcp_auth_without_a_store(monkeypatch):
    """حوكمة #408 كالمنصّة: خادم MCP في الإنتاج بلا Redis لا يُقلِع (الاستيراد يرفع)."""
    import shared

    monkeypatch.setattr(shared, "__path__", [str(ROOT / "shared"), str(MCP / "shared")])
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.delenv("DENYLIST_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    try:
        with pytest.raises(RuntimeError, match="Redis"):
            _exec("_s5_mcp_oauth_prod", MCP / "shared/oauth_middleware.py")
    finally:
        sys.modules.pop("_s5_mcp_oauth_prod", None)
