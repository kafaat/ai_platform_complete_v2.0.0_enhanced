"""S5 (audit 2026-11-01) — JWT consumers outside the platform honour auth's revocation.

**Fault on origin/main cc0d2e295:** ``guardrails-engine`` (``_gr_verify`` / ``_gr_authn``),
``supervisor-agent`` (``_get_current_user``) and ``notification-agent`` (``_validate_ws_token``)
decoded the token and checked its issuer, nothing else. auth revokes on logout (``jti``) and
on a role change / password change / deactivation (per-user ``token_floor``), and the platform
honours both; these three did not, so an expert demoted to farmer kept approving HIL actions
with the old ``role`` claim until the token expired.

**Fix:** ``shared/security/token_revocation.py`` — the platform's rule and policy as is (same keys,
``int(iat) < int(floor)``, fail-open per check, production refuses to start without the store).

Each service is checked with a fake store: revoked jti ⇒ rejected · issued before the floor ⇒
rejected · valid token ⇒ accepted.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
import uuid
from pathlib import Path

import jwt
import pytest

from tests_v9 import service_module

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SECRET = "s5-revocation-test-secret-0123456789-abcdefghijklmnop"
TENANT = "11111111-1111-1111-1111-111111111111"


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


def _token(**over) -> tuple[str, dict]:
    now = int(time.time())
    claims = {
        "sub": "42",
        "tenant_id": TENANT,
        "role": "expert",
        "iss": "sahool-auth",
        "aud": "sahool",
        "iat": now - 60,
        "exp": now + 600,
        "jti": uuid.uuid4().hex,
        **over,
    }
    return jwt.encode(claims, SECRET, algorithm="HS256"), claims


def _cases(claims):
    """(store, should_be_rejected) — revoked jti · below floor · valid (two unrelated revocations)."""
    return {
        "revoked_jti": (FakeStore(revoked={claims["jti"]}), True),
        "issued_before_floor": (FakeStore(floors={"42": claims["iat"] + 1}), True),
        "valid": (FakeStore(revoked={"other-jti"}, floors={"42": claims["iat"]}), False),
    }


CASES = ("revoked_jti", "issued_before_floor", "valid")


@pytest.fixture
def jwt_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.delenv("DENYLIST_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("SAHOOL_ACCESS_TOKEN_CLAIM_POLICY", raising=False)


def _load_service(rel: str, attrs: tuple[str, ...]):
    service_module.purge_generic_modules()
    try:
        return service_module.load_service_main(str(ROOT / rel), required_attrs=attrs)
    finally:
        service_module.purge_generic_modules()


# ── the services ──────────────────────────────────────────────────────────────


@pytest.fixture
def guardrails(jwt_env):
    return _load_service("services/guardrails-engine", ("app", "_gr_verify", "_gr_authn"))


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("dep", ["_gr_verify", "_gr_authn"])
def test_guardrails_hil_auth_honours_revocation(guardrails, monkeypatch, dep, case):
    from fastapi import HTTPException

    token, claims = _token()
    store, rejected = _cases(claims)[case]
    monkeypatch.setattr(guardrails, "_REVOCATION", store, raising=False)
    verify = getattr(guardrails, dep)
    if rejected:
        with pytest.raises(HTTPException) as exc:
            verify(authorization="Bearer " + token)
        assert exc.value.status_code == 401
    else:
        assert verify(authorization="Bearer " + token)["sub"] == "42"


@pytest.fixture
def supervisor(jwt_env):
    return _load_service("services/supervisor-agent", ("app", "_get_current_user"))


@pytest.mark.parametrize("case", CASES)
def test_supervisor_auth_honours_revocation(supervisor, monkeypatch, case):
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    token, claims = _token()
    store, rejected = _cases(claims)[case]
    monkeypatch.setattr(supervisor, "_REVOCATION", store, raising=False)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    if rejected:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(supervisor._get_current_user(creds))
        assert exc.value.status_code == 401
    else:
        assert asyncio.run(supervisor._get_current_user(creds))["sub"] == "42"


@pytest.fixture
def notification(jwt_env):
    spec = importlib.util.spec_from_file_location(
        "notification_s5_under_test", ROOT / "agents/notification/agent.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("case", CASES)
def test_notification_ws_auth_honours_revocation(notification, monkeypatch, case):
    token, claims = _token()
    store, rejected = _cases(claims)[case]
    monkeypatch.setattr(notification, "_REVOCATION", store, raising=False)
    if rejected:
        with pytest.raises(ValueError):
            notification._validate_ws_token(token)
    else:
        assert notification._validate_ws_token(token)["sub"] == "42"


def test_services_are_fail_open_on_a_store_error_like_the_platform(
    guardrails, notification, monkeypatch
):
    token, _ = _token()
    monkeypatch.setattr(guardrails, "_REVOCATION", BrokenStore())
    monkeypatch.setattr(notification, "_REVOCATION", BrokenStore())
    assert guardrails._gr_verify(authorization="Bearer " + token)["sub"] == "42"
    assert notification._validate_ws_token(token)["sub"] == "42"


# ── the shared module: the platform's rule and policy ─────────────────────────


def _platform_denylist():
    path = ROOT / "services/sahool-platform/core/jwt_denylist.py"
    spec = importlib.util.spec_from_file_location("platform_jwt_denylist_s5", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_keys_and_url_rule_are_the_platforms():
    from shared.security import token_revocation as tr

    p = _platform_denylist()
    assert tr.JTI_REVOKED_KEY == p.JTI_REVOKED_KEY == "sahool:jti:revoked:{jti}"
    assert tr.TOKEN_FLOOR_KEY == p.TOKEN_FLOOR_KEY == "sahool:user:token_floor:{sub}"
    for env in (
        {},
        {"REDIS_URL": "redis://cache"},
        {"REDIS_URL": "redis://cache", "DENYLIST_REDIS_URL": "redis://state"},
        {"REDIS_URL": "redis://cache", "DENYLIST_REDIS_URL": "  "},
    ):
        assert tr.revocation_redis_url(env) == p.denylist_redis_url(env), env


@pytest.mark.parametrize(
    "payload,floor",
    [
        ({"sub": "42", "iat": 99}, 100),
        ({"sub": "42", "iat": 100}, 100),
        ({"sub": "42", "iat": 101}, 100),
        ({"sub": "42", "iat": 99}, None),
        ({"iat": 99}, 100),
        ({"sub": "42"}, 100),
        ({"sub": 42, "iat": 99.0}, 100),
    ],
)
def test_floor_rule_matches_the_platform(payload, floor):
    from shared.security import token_revocation as tr

    p = _platform_denylist()
    platform_store = p.InMemoryDenylist()
    if floor is not None:
        platform_store.set_token_floor("42", floor)
    ours = FakeStore(floors={"42": floor} if floor is not None else {})
    assert tr.is_token_below_floor(ours, payload) is p.is_token_below_floor(platform_store, payload)


def test_store_errors_and_missing_inputs_fail_open():
    from shared.security import token_revocation as tr

    assert tr.token_is_revoked(BrokenStore(), {"sub": "1", "iat": 1, "jti": "j"}) is False
    assert tr.token_is_revoked(None, {"sub": "1", "iat": 1, "jti": "j"}) is False
    assert tr.token_is_revoked(FakeStore(revoked={"j"}), {"sub": "1"}) is False


class _FakeRedis:
    def __init__(self, kv=None, fail_ping=False):
        self.kv = dict(kv or {})
        self.fail_ping = fail_ping
        self.calls = []

    def ping(self):
        if self.fail_ping:
            raise ConnectionError("unreachable")
        return True

    def exists(self, key):
        self.calls.append(("exists", key))
        return int(key in self.kv)

    def get(self, key):
        self.calls.append(("get", key))
        return self.kv.get(key)


def test_redis_store_reads_auths_keys_read_only():
    from shared.security import token_revocation as tr

    fake = _FakeRedis({"sahool:jti:revoked:j1": "1", "sahool:user:token_floor:42": b"200"})
    seen = {}

    def from_url(url, **kw):
        seen.update(url=url, **kw)
        return fake

    store = tr.build_revocation_store(
        {"DENYLIST_REDIS_URL": "redis://state", "REDIS_URL": "redis://cache"},
        redis_from_url=from_url,
    )
    assert seen["url"] == "redis://state"
    assert tr.token_is_revoked(store, {"jti": "j1"}) is True
    assert tr.token_is_revoked(store, {"jti": "j2", "sub": "42", "iat": 199}) is True
    assert tr.token_is_revoked(store, {"jti": "j2", "sub": "42", "iat": 200}) is False
    assert {c for c, _ in fake.calls} == {"exists", "get"}


@pytest.mark.parametrize("env_name", ["production", "prod"])
def test_production_refuses_to_start_without_a_reachable_store(env_name):
    """حوكمة #408 كالمنصّة (``_build_denylist``): الإنتاج بلا Redis ⇒ رفض الإقلاع."""
    from shared.security import token_revocation as tr

    with pytest.raises(RuntimeError):
        tr.build_revocation_store({"SAHOOL_ENV": env_name})
    with pytest.raises(RuntimeError):
        tr.build_revocation_store(
            {"SAHOOL_ENV": env_name, "REDIS_URL": "redis://x"},
            redis_from_url=lambda *a, **k: _FakeRedis(fail_ping=True),
        )


def test_outside_production_a_missing_store_disables_the_check():
    from shared.security import token_revocation as tr

    assert tr.build_revocation_store({}) is None
    assert (
        tr.build_revocation_store(
            {"REDIS_URL": "redis://x"},
            redis_from_url=lambda *a, **k: _FakeRedis(fail_ping=True),
        )
        is None
    )
