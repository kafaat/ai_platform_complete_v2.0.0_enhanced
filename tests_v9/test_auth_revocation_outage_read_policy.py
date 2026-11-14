"""Auth: a revocation store that fails at runtime lets safe reads through and refuses writes.

**Owner decision (14 November 2026, ``docs/AUTH_DENYLIST_DESIGN.md``).** Since #1427,
``main.get_current_user`` answered 503 for every request whose revocation check could not be
performed. Now, through ``session_tokens.session_revoked``:

* revocation state unknown (the store raised) and a safe method (GET, HEAD, OPTIONS) => the
  request proceeds, with a WARNING carrying ``REVOCATION-STORE-UNAVAILABLE-READ-ALLOWED``;
* unknown and any other method (POST, PUT, PATCH, DELETE), or a direct call without a request
  (``mfa_enrollment.user_for``) => 503, in every environment;
* a token proven revoked (jti or user floor) => 401 for every method, even while the other
  check fails;
* Redis absent since boot (``_redis is None``, development only: production refuses to start)
  is not an outage and stays unchanged.

The store here is an async client whose every command raises
``redis.exceptions.ConnectionError``, as redis.asyncio does when the server does not answer.
The live counterpart on a real Postgres and redis.asyncio client is
``test_auth_admin_authz_live_pg_redis.py`` (``GET /v1/auth/users`` under an unreachable Redis).
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
AUTH_DIR = os.path.join(ROOT, "services/auth")
REASON = "REVOCATION-STORE-UNAVAILABLE-READ-ALLOWED"
SAFE = ("GET", "HEAD", "OPTIONS")
WRITES = ("POST", "PUT", "PATCH", "DELETE")


@pytest.fixture(scope="module")
def m():
    pytest.importorskip("jwt")
    pytest.importorskip("redis")
    pytest.importorskip("fastapi")
    # Same module key as test_auth_session_revocation: one import of the service per process.
    if "auth_main_sessions_test" in sys.modules:
        return sys.modules["auth_main_sessions_test"]
    if AUTH_DIR not in sys.path:
        sys.path.insert(0, AUTH_DIR)
    spec = importlib.util.spec_from_file_location(
        "auth_main_sessions_test", os.path.join(AUTH_DIR, "main.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["auth_main_sessions_test"] = mod
    return mod


class _Down:
    """redis.asyncio stand-in: every command raises as an unreachable server does."""

    async def _down(self, *_a, **_k):
        import redis

        raise redis.exceptions.ConnectionError("Error 111 connecting to sahool-redis-state:6379")

    exists = get = setex = ping = _down


class _JtiRevokedFloorDown:
    """The jti is on the denylist; the floor read fails. Proof must win: 401."""

    async def exists(self, *_a):
        return 1

    async def get(self, *_a):
        import redis

        raise redis.exceptions.ConnectionError("floor read failed")


class _Healthy:
    def __init__(self, revoked: bool = False):
        self.revoked = revoked

    async def exists(self, *_a):
        return 1 if self.revoked else 0

    async def get(self, *_a):
        return None


@pytest.fixture
def client(m):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    def _ok(user=Depends(m.get_current_user)):
        return {"sub": user["sub"]}

    app.api_route("/thing", methods=[*SAFE, *WRITES])(_ok)
    return TestClient(app)


def _token(m) -> str:
    token, _ = m.create_access_token(7, "u7@example.test", "farmer", "U", "t-1")
    return token


def _call(client, m, method: str):
    return client.request(method, "/thing", headers={"Authorization": f"Bearer {_token(m)}"})


@pytest.mark.parametrize("env", ["production", "development"])
@pytest.mark.parametrize("method", SAFE)
def test_unknown_revocation_state_lets_a_safe_method_through_with_reason(
    m, client, monkeypatch, caplog, method, env
):
    monkeypatch.setenv("SAHOOL_ENV", env)
    monkeypatch.setattr(m, "_redis", _Down())
    with caplog.at_level(logging.WARNING, logger="auth"):
        r = _call(client, m, method)
    assert r.status_code == 200, r.text
    if method != "HEAD":
        assert r.json() == {"sub": "7"}
    assert any(REASON in rec.getMessage() and method in rec.getMessage() for rec in caplog.records)


@pytest.mark.parametrize("env", ["production", "development"])
@pytest.mark.parametrize("method", WRITES)
def test_unknown_revocation_state_refuses_an_unsafe_method_with_503(
    m, client, monkeypatch, caplog, method, env
):
    monkeypatch.setenv("SAHOOL_ENV", env)
    monkeypatch.setattr(m, "_redis", _Down())
    with caplog.at_level(logging.WARNING, logger="auth"):
        r = _call(client, m, method)
    assert r.status_code == 503, r.text
    assert r.json()["detail"] == "تعذّر التحقّق من إبطال التوكن — أعد المحاولة"
    assert not any(REASON in rec.getMessage() for rec in caplog.records)


async def test_a_direct_call_without_a_request_is_not_a_read(m, monkeypatch):
    """``mfa_enrollment.user_for`` calls get_current_user(credentials) without a request."""
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    monkeypatch.setattr(m, "_redis", _Down())
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=_token(m))
    with pytest.raises(HTTPException) as exc:
        await m.get_current_user(creds)
    assert exc.value.status_code == 503


@pytest.mark.parametrize("method", SAFE + WRITES)
def test_proven_revocation_is_401_for_every_method_even_with_the_other_check_down(
    m, client, monkeypatch, method
):
    monkeypatch.setattr(m, "_redis", _JtiRevokedFloorDown())
    assert _call(client, m, method).status_code == 401


@pytest.mark.parametrize("method", SAFE + WRITES)
def test_healthy_store_revoked_is_401_and_not_revoked_is_200(m, client, monkeypatch, method):
    monkeypatch.setattr(m, "_redis", _Healthy(revoked=True))
    assert _call(client, m, method).status_code == 401
    monkeypatch.setattr(m, "_redis", _Healthy(revoked=False))
    assert _call(client, m, method).status_code == 200


@pytest.mark.parametrize("method", SAFE + WRITES)
def test_redis_absent_since_boot_is_unchanged(m, client, monkeypatch, method):
    """Development without Redis at boot: the checks are skipped as before (no 503, no 401)."""
    monkeypatch.setattr(m, "_redis", None)
    assert _call(client, m, method).status_code == 200


async def test_session_revoked_contract():
    """The policy itself, without the service: safe verbs by name, anything else refused."""
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "auth_session_tokens_policy_test", os.path.join(AUTH_DIR, "session_tokens.py")
    )
    st = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(st)
    from fastapi import HTTPException

    assert st.READ_ALLOWED_REASON == REASON
    assert frozenset(SAFE) == st.SAFE_METHODS

    async def boom():
        raise ConnectionError("down")

    async def yes():
        return True

    for verb in ("GET", "head", "OPTIONS"):
        assert await st.session_revoked(boom(), request=SimpleNamespace(method=verb)) is False
        assert await st.session_revoked(yes(), boom(), request=SimpleNamespace(method=verb))
    for req in (None, SimpleNamespace(method="POST"), SimpleNamespace(method="TRACE")):
        with pytest.raises(HTTPException) as exc:
            await st.session_revoked(boom(), request=req)
        assert exc.value.status_code == 503
