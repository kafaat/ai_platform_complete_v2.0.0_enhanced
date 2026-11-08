"""S5 for the physical consumer: a revoked token cannot move a device.

ACTUATOR-SERVICE-IGNORES-JWT-REVOCATION-01. auth revokes on logout (``sahool:jti:revoked:{jti}``)
and revokes every session of a user on a password, role or account change
(``sahool:user:token_floor:{sub}``). The platform honours both but fails open. The actuator
honoured neither, so a manager who logged out, or whose role was lowered, kept opening
valves until the token expired.

These tests pin four things:

1. the key schema is the platform's, so the two readers cannot drift apart;
2. a revoked or floor-expired token is refused with 401 *before* the device lookup;
3. in production an unknown revocation state is a 503, never a command;
4. outside production with no store configured the check is skipped, so local development
   and the existing unit tests keep working. That skip is logged, not silent.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "actuator-service"

sys.path.insert(0, str(ROOT))
from shared.security import token_revocation as tr  # noqa: E402

_DENYLIST_SPEC = importlib.util.spec_from_file_location(
    "platform_jwt_denylist_for_parity",
    ROOT / "services" / "sahool-platform" / "core" / "jwt_denylist.py",
)
assert _DENYLIST_SPEC is not None and _DENYLIST_SPEC.loader is not None
platform_denylist = importlib.util.module_from_spec(_DENYLIST_SPEC)
_DENYLIST_SPEC.loader.exec_module(platform_denylist)


class FakeStore:
    """A Redis stand-in holding only the two key families the check reads."""

    def __init__(self, revoked=(), floors=None, fail=False):
        self.revoked = {tr.JTI_REVOKED_KEY.format(jti=j) for j in revoked}
        self.floors = {
            tr.TOKEN_FLOOR_KEY.format(sub=s): str(v).encode() for s, v in (floors or {}).items()
        }
        self.fail = fail
        self.calls: list[str] = []

    def exists(self, key):
        self.calls.append(f"exists {key}")
        if self.fail:
            raise ConnectionError("store down")
        return 1 if key in self.revoked else 0

    def get(self, key):
        self.calls.append(f"get {key}")
        if self.fail:
            raise ConnectionError("store down")
        return self.floors.get(key)


CLAIMS = {"sub": "u1", "jti": "j1", "iat": 1_000, "role": "manager", "tenant_id": "t1"}


# ───────────────────────────────────────────── the shared check (pure)


def test_the_key_schema_is_the_platforms() -> None:
    assert tr.JTI_REVOKED_KEY == platform_denylist.JTI_REVOKED_KEY
    assert tr.TOKEN_FLOOR_KEY == platform_denylist.TOKEN_FLOOR_KEY


def test_the_store_url_resolution_is_the_platforms() -> None:
    for env in (
        {},
        {"REDIS_URL": "redis://a"},
        {"DENYLIST_REDIS_URL": "redis://b", "REDIS_URL": "redis://a"},
        {"DENYLIST_REDIS_URL": "  ", "REDIS_URL": "redis://a"},
    ):
        assert tr.revocation_redis_url(env) == platform_denylist.denylist_redis_url(env), env


def test_a_live_token_may_act() -> None:
    assert tr.revocation_reason(FakeStore(), CLAIMS) is None


def test_a_logged_out_token_is_revoked() -> None:
    assert tr.revocation_reason(FakeStore(revoked=["j1"]), CLAIMS) == "revoked"


def test_a_token_older_than_the_floor_is_refused_and_the_boundary_matches_the_platform() -> None:
    assert tr.revocation_reason(FakeStore(floors={"u1": 1_001}), CLAIMS) == "below_token_floor"
    # iat == floor is still valid on the platform (`int(iat) < int(floor)`), so here too.
    assert tr.revocation_reason(FakeStore(floors={"u1": 1_000}), CLAIMS) is None


def test_no_store_no_jti_or_a_store_error_is_unknown_not_allowed() -> None:
    with pytest.raises(tr.RevocationUnavailable):
        tr.revocation_reason(None, CLAIMS)
    with pytest.raises(tr.RevocationUnavailable):
        tr.revocation_reason(FakeStore(), {k: v for k, v in CLAIMS.items() if k != "jti"})
    with pytest.raises(tr.RevocationUnavailable):
        tr.revocation_reason(FakeStore(fail=True), CLAIMS)


# ───────────────────────────────────────────── wired into the actuator


def _stub_missing_dependencies() -> list[str]:
    inserted: list[str] = []
    if "asyncpg" not in sys.modules:
        stub = types.ModuleType("asyncpg")
        stub.Pool = object

        async def _create_pool(*_a, **_k):  # pragma: no cover
            raise RuntimeError("asyncpg stubbed")

        stub.create_pool = _create_pool
        sys.modules["asyncpg"] = stub
        inserted.append("asyncpg")
    if "aiomqtt" not in sys.modules:
        try:
            import aiomqtt  # noqa: F401
        except ImportError:
            stub = types.ModuleType("aiomqtt")
            stub.Client = object
            sys.modules["aiomqtt"] = stub
            inserted.append("aiomqtt")
    return inserted


@pytest.fixture
def actuator(monkeypatch):
    stubbed = _stub_missing_dependencies()
    monkeypatch.setenv("ACTUATOR_MODE", "simulation")
    monkeypatch.setenv("JWT_SECRET_KEY", "t" * 32)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("DENYLIST_REDIS_URL", raising=False)
    monkeypatch.syspath_prepend(str(SERVICE))
    monkeypatch.syspath_prepend(str(ROOT))
    sys.modules.pop("actuator_runtime", None)
    try:
        spec = importlib.util.spec_from_file_location(
            "actuator_runtime", SERVICE / "actuator_runtime.py"
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["actuator_runtime"] = mod
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.modules.pop("actuator_runtime", None)
        for name in stubbed:
            sys.modules.pop(name, None)


class _PoolThatMustNotBeReached:
    """A device lookup after a refused token would be the defect itself."""

    def acquire(self):  # pragma: no cover - reaching it fails the test
        raise AssertionError("device lookup reached with a token that may not act")


def _pool_owning_the_device():
    class _Conn:
        async def fetchrow(self, *_a):
            return {"tenant_id": "t1", "field_id": "f1"}

    class _Ctx:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Ctx()

    return _Pool()


def _use_store(actuator, monkeypatch, store) -> None:
    monkeypatch.setattr(actuator, "_revocation_client", lambda: store)


async def test_a_revoked_token_cannot_move_a_device(actuator, monkeypatch) -> None:
    from fastapi import HTTPException

    _use_store(actuator, monkeypatch, FakeStore(revoked=["j1"]))
    monkeypatch.setattr(actuator, "_pool", _PoolThatMustNotBeReached())
    with pytest.raises(HTTPException) as exc:
        await actuator._authorize_device_control(dict(CLAIMS), "valve-1")
    assert exc.value.status_code == 401


async def test_a_token_below_the_floor_cannot_move_a_device(actuator, monkeypatch) -> None:
    from fastapi import HTTPException

    _use_store(actuator, monkeypatch, FakeStore(floors={"u1": 2_000}))
    monkeypatch.setattr(actuator, "_pool", _PoolThatMustNotBeReached())
    with pytest.raises(HTTPException) as exc:
        await actuator._authorize_device_control(dict(CLAIMS), "valve-1")
    assert exc.value.status_code == 401


async def test_a_live_token_still_reaches_the_device(actuator, monkeypatch) -> None:
    store = FakeStore()
    _use_store(actuator, monkeypatch, store)
    monkeypatch.setattr(actuator, "_pool", _pool_owning_the_device())
    assert await actuator._authorize_device_control(dict(CLAIMS), "valve-1") == "f1"
    assert store.calls, "the store was never asked, so revocation was not checked"


@pytest.mark.parametrize(
    "store, claims",
    [
        (None, CLAIMS),
        (FakeStore(fail=True), CLAIMS),
        (FakeStore(), {k: v for k, v in CLAIMS.items() if k != "jti"}),
    ],
    ids=["no-store", "store-down", "no-jti"],
)
async def test_production_refuses_when_revocation_state_is_unknown(
    actuator, monkeypatch, store, claims
) -> None:
    from fastapi import HTTPException

    monkeypatch.setenv("SAHOOL_ENV", "production")
    _use_store(actuator, monkeypatch, store)
    monkeypatch.setattr(actuator, "_pool", _PoolThatMustNotBeReached())
    with pytest.raises(HTTPException) as exc:
        await actuator._authorize_device_control(dict(claims), "valve-1")
    assert exc.value.status_code == 503


async def test_production_refuses_when_the_client_cannot_be_built(actuator, monkeypatch) -> None:
    from fastapi import HTTPException

    def _boom():
        raise ValueError("bad url")

    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.setattr(actuator, "_revocation_client", _boom)
    monkeypatch.setattr(actuator, "_pool", _PoolThatMustNotBeReached())
    with pytest.raises(HTTPException) as exc:
        await actuator._authorize_device_control(dict(CLAIMS), "valve-1")
    assert exc.value.status_code == 503


async def test_outside_production_no_store_skips_the_check_and_says_so(
    actuator, monkeypatch, caplog
) -> None:
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.setattr(actuator, "_pool", _pool_owning_the_device())
    with caplog.at_level(logging.WARNING):
        assert await actuator._authorize_device_control(dict(CLAIMS), "valve-1") == "f1"
    assert "token revocation not checked" in caplog.text


async def test_outside_production_a_configured_store_is_still_enforced(
    actuator, monkeypatch
) -> None:
    from fastapi import HTTPException

    monkeypatch.setenv("SAHOOL_ENV", "development")
    _use_store(actuator, monkeypatch, FakeStore(revoked=["j1"]))
    monkeypatch.setattr(actuator, "_pool", _PoolThatMustNotBeReached())
    with pytest.raises(HTTPException) as exc:
        await actuator._authorize_device_control(dict(CLAIMS), "valve-1")
    assert exc.value.status_code == 401


def test_the_client_is_not_built_at_import(actuator) -> None:
    """S5 was held back because a consumer refusing to *start* takes the service down."""
    assert actuator._revocation_client_cache == []
