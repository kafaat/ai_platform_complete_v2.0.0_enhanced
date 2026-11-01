"""S1: market MCP REST routes verify tokens with the server-configured algorithm only.

``market_server.verify_token`` decoded every REST token with HS256 and ``JWT_SECRET``,
even when ``JWT_PUBLIC_KEY`` (RS256) was configured. Anyone holding the shared HS
secret could then mint a token and create buy/sell orders in any tenant. The REST
routes now share ``access_token_key``/issuer/tenant checks with ``require_scope``:
RS256 configured ⇒ HS256 rejected; tenant comes from the verified token only.

Drives the real FastAPI app in-process; only the DB connection is replaced.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "services/mcp_servers"
SECRET = "x" * 40
ORDER = {"items": [{"product_name": "urea", "quantity": 1, "max_unit_price_usd": 1}]}
WRITE = "market:read market:write"


def _load(name: str, path: Path):
    current = sys.modules.get(name)
    if current is not None:
        assert Path(getattr(current, "__file__", "")).resolve() == path.resolve()
        return current
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def rsa_key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return key, public.decode()


class _FakeConn:
    def __init__(self):
        self.statements: list[tuple] = []

    async def fetchval(self, sql, *params):
        self.statements.append((sql, params))
        return "00000000-0000-0000-0000-0000000000aa"

    async def execute(self, sql, *params):
        self.statements.append((sql, params))


@pytest.fixture
def market(monkeypatch, rsa_key):
    """Container import layout, RS256 configured while JWT_SECRET is still present."""
    import shared

    monkeypatch.setattr(shared, "__path__", [str(ROOT / "shared"), str(MCP / "shared")])
    monkeypatch.syspath_prepend(str(MCP))
    oauth = _load("_live_mcp_oauth", MCP / "shared/oauth_middleware.py")
    monkeypatch.setitem(sys.modules, "shared.oauth_middleware", oauth)
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("JWT_PUBLIC_KEY", rsa_key[1])
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.delenv("SAHOOL_ALLOW_HS256_IN_PROD", raising=False)
    monkeypatch.delenv("MARKET_AUTO_APPROVE_BELOW_USD", raising=False)
    module = _load("_s1_market_server", MCP / "market_server.py")
    tenants: list[str | None] = []

    @asynccontextmanager
    async def fake_tenant_connection(tenant_id):
        tenants.append(tenant_id)
        yield _FakeConn()

    monkeypatch.setattr(module, "tenant_connection", fake_tenant_connection)
    return module, tenants


def _claims(tenant="tenant-a", scope=WRITE, **over):
    claims = {
        "sub": "42",
        "tenant_id": tenant,
        "scope": scope,
        "iss": "sahool-auth",
        "aud": "sahool",
        "exp": int(time.time()) + 300,
    }
    for k, v in over.items():
        if v is None:
            claims.pop(k, None)
        else:
            claims[k] = v
    return claims


def _hs256(**kw) -> str:
    import jwt

    return jwt.encode(_claims(**kw), SECRET, algorithm="HS256")


def _rs256(rsa_key, **kw) -> str:
    import jwt

    return jwt.encode(_claims(**kw), rsa_key[0], algorithm="RS256")


def _post(module, path, body, token):
    from fastapi.testclient import TestClient

    client = TestClient(module.app, raise_server_exceptions=False)
    return client.post(path, json=body, headers={"Authorization": f"Bearer {token}"})


@pytest.mark.parametrize(
    "path,body",
    [
        ("/v1/procurement", ORDER),
        ("/v1/sales", {"crop_type": "wheat", "quantity_kg": 10, "price_per_kg_usd": 1}),
    ],
)
def test_hs256_token_rejected_when_rs256_is_configured(market, path, body):
    module, tenants = market
    response = _post(module, path, body, _hs256())
    assert response.status_code == 401, response.text
    assert tenants == [], "an HS256 token must not reach the order write path"


def test_hs256_token_rejected_on_rest_reads_too(market):
    from fastapi.testclient import TestClient

    module, tenants = market
    client = TestClient(module.app, raise_server_exceptions=False)
    response = client.get("/v1/products", headers={"Authorization": f"Bearer {_hs256()}"})
    assert response.status_code == 401, response.text
    assert tenants == []


def test_valid_rs256_token_is_accepted(market, rsa_key):
    module, tenants = market
    response = _post(module, "/v1/procurement", ORDER, _rs256(rsa_key))
    assert response.status_code == 200, response.text
    assert tenants == ["tenant-a"]


@pytest.mark.parametrize("mode", ["rs256", "hs256-dev"])
@pytest.mark.parametrize("tenant", [None, "", "../tenant-b"], ids=["absent", "empty", "bad"])
def test_token_without_valid_tenant_is_rejected(market, rsa_key, monkeypatch, mode, tenant):
    module, tenants = market
    if mode == "rs256":
        token = _rs256(rsa_key, tenant=tenant)
    else:  # HS256 is still legitimate in development without JWT_PUBLIC_KEY
        monkeypatch.delenv("JWT_PUBLIC_KEY")
        monkeypatch.setenv("SAHOOL_ENV", "development")
        token = _hs256(tenant=tenant)
    response = _post(module, "/v1/procurement", ORDER, token)
    assert response.status_code in (400, 401), response.text
    assert tenants == [], "a token without a valid tenant must not reach the write path"


def test_token_from_unknown_issuer_is_rejected(market, rsa_key):
    module, tenants = market
    response = _post(module, "/v1/procurement", ORDER, _rs256(rsa_key, iss="other-service"))
    assert response.status_code == 401, response.text
    assert tenants == []


def test_cross_tenant_order_is_denied(market, rsa_key, monkeypatch):
    module, tenants = market
    # The body's tenant_id never selects the tenant: the order lands in the token's tenant.
    body = {**ORDER, "tenant_id": "tenant-b"}
    response = _post(module, "/v1/procurement", body, _rs256(rsa_key))
    assert response.status_code == 200, response.text
    assert tenants == ["tenant-a"]

    # A field owned by another tenant cannot be attached to the caller's order.
    async def owner_is_b(field_id):
        return "tenant-b"

    monkeypatch.setattr(module.market_db_authz, "field_owner_tenant", owner_is_b)
    response = _post(module, "/v1/procurement", {**body, "field_id": "f-b"}, _rs256(rsa_key))
    assert response.status_code == 403, response.text
    assert tenants == ["tenant-a"]
