"""Decision-service _service_token_guard middleware — behavioral contract (open-ledger #2).

The service is reachable directly inside the cluster on its raw internal port. When
DECISION_SERVICE_AUTH_TOKEN is configured (or production is armed) every non-probe request MUST
present the shared bearer token, so a co-located service can no longer spoof tenant/actor identity
headers. These 8 tests pin that contract, including the production restriction of the exemption set
to the health probes.

No DB, no network — the middleware runs before any route. TestClient is constructed WITHOUT the
context manager so the app lifespan (which hard-fails an unauthenticated production start) does not
run; we exercise the middleware branch directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

# A path that no route serves: an authorized request reaches routing and 404s; the point is only
# whether the MIDDLEWARE lets it through (not 401/503).
UNROUTED = "/v1/__does_not_exist__"
TOKEN = "s3cr3t-service-token"


def _client(monkeypatch, *, token: str | None, require: bool = False, prod: bool = False):
    monkeypatch.setenv("SAHOOL_ENV", "production" if prod else "development")
    monkeypatch.setenv("DECISION_REQUIRE_AUTH_TOKEN", "true" if require else "")
    if token is None:
        monkeypatch.delenv("DECISION_SERVICE_AUTH_TOKEN", raising=False)
    else:
        monkeypatch.setenv("DECISION_SERVICE_AUTH_TOKEN", token)
    import main
    from fastapi.testclient import TestClient

    return TestClient(main.app)


# 1 — dev, no token configured, not required ⇒ the guard is a no-op (existing gateway-trusted flow).
def test_development_without_token_is_allowed(monkeypatch):
    c = _client(monkeypatch, token=None)
    assert c.get(UNROUTED).status_code == 404  # reached routing, not blocked by the guard


# 2 — required mode but the token is absent ⇒ FAIL CLOSED in the middleware (503), never open.
def test_required_mode_missing_token_fails_closed_in_middleware(monkeypatch):
    c = _client(monkeypatch, token=None, require=True)
    r = c.get(UNROUTED)
    assert r.status_code == 503 and "authentication unavailable" in r.json()["detail"]


# 3 — token configured, no Authorization header ⇒ 401.
def test_missing_authorization_header_is_401(monkeypatch):
    c = _client(monkeypatch, token=TOKEN)
    assert c.get(UNROUTED).status_code == 401


# 4 — token configured, wrong bearer ⇒ 401 (constant-time compare, still a reject).
def test_wrong_token_is_401(monkeypatch):
    c = _client(monkeypatch, token=TOKEN)
    r = c.get(UNROUTED, headers={"Authorization": "Bearer not-the-token"})
    assert r.status_code == 401


# 5 — token configured, correct bearer ⇒ the guard passes the request through to routing.
def test_correct_token_is_accepted(monkeypatch):
    c = _client(monkeypatch, token=TOKEN)
    r = c.get(UNROUTED, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 404  # authorized ⇒ reached routing, not 401


# 6 — the "Bearer" scheme is matched case-insensitively.
def test_bearer_prefix_is_case_insensitive(monkeypatch):
    c = _client(monkeypatch, token=TOKEN)
    r = c.get(UNROUTED, headers={"Authorization": f"BEARER {TOKEN}"})
    assert r.status_code == 404


# 7 — health probes are exempt even with a token configured, and trailing slashes normalize.
def test_probe_paths_exempt_and_allow_trailing_slash(monkeypatch):
    c = _client(monkeypatch, token=TOKEN)
    assert c.get("/healthz").status_code != 401
    assert c.get("/readyz/").status_code != 401  # trailing slash still exempt
    assert c.get("/livez").status_code != 401


# 8 — PRODUCTION restricts the exemption set to the probes: a docs path is NOT exempt (401 without a
# token), while a probe still is. This is the negative proof for the prod-exemption tightening.
def test_production_restricts_exemptions_to_probes(monkeypatch):
    c = _client(monkeypatch, token=TOKEN, prod=True)
    # docs path in production ⇒ not exempt ⇒ the guard demands the token.
    assert c.get("/openapi.json").status_code == 401
    # a health probe stays exempt in production.
    assert c.get("/healthz").status_code != 401
