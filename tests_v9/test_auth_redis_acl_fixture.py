"""AUTH-REDIS-ACL-FIXTURE-CREDENTIAL-PRECEDENCE-01: exercise the real URL parser.

Only disconnected clients are constructed; these unit cases need no Redis or PG.
The live fixture separately proves authentication, reads and actual SETEX denial.
"""

import asyncio

import pytest
import redis.asyncio as aioredis

from tests_v9.test_auth_admin_authz_live_pg_redis import _redis_acl_client

pytestmark = pytest.mark.unit

_PLAIN = (str, bytes, int, float, bool, type(None))


def _comparable(options: dict) -> dict:
    """Plain option values compare exactly; per-pool runtime objects compare by type.

    redis>=8 puts objects into ``connection_kwargs`` that each new pool creates afresh
    (``HImportRegistry``, ``AsyncMaintNotificationsPoolHandler``) and that define no
    ``__eq__``, so two independently built pools never compare equal even when every
    connection option matches. The requirements pin only ``redis>=5.0.0``, so the
    comparison must not depend on which release CI resolves. Every key must still be
    present on both sides, and a dropped or altered option value still fails.
    """
    return {k: _comparable_value(v) for k, v in options.items()}


def _comparable_value(value):
    """Containers compare element by element; only opaque objects fall back to their type."""
    if isinstance(value, _PLAIN):
        return value
    if isinstance(value, (list, tuple)):
        return (type(value), tuple(_comparable_value(v) for v in value))
    if isinstance(value, dict):
        return (dict, {k: _comparable_value(v) for k, v in value.items()})
    if type(value).__eq__ is not object.__eq__:
        return value  # defines value equality (e.g. a dataclass): compare it as such
    return type(value)


@pytest.mark.parametrize(
    "url",
    [
        "redis://fixture.invalid:6380/2?socket_timeout=0.25&max_connections=7",
        "redis://:url-secret@fixture.invalid:6380/2",
        "redis://url-user:url-secret@fixture.invalid:6380/2",
        "redis://fixture.invalid:6380/2?username=query-user&password=query-secret&db=4",
        "redis://url-user:url-secret@fixture.invalid:6380/2?username=query-user&password=query-secret&health_check_interval=11",
        "rediss://url%2Duser:url%2Dsecret@[::1]:6380/2?socket_connect_timeout=0.5&client_name=fixture-client",
        "unix:///tmp/never-opened-auth-fixture.sock?username=query-user&password=query-secret&db=4",
    ],
    ids=[
        "no-auth",
        "url-password",
        "url-user-password",
        "query-auth",
        "mixed-auth",
        "tls-ipv6",
        "unix-query",
    ],
)
def test_acl_identity_overrides_url_auth_but_preserves_connection_options(url):
    baseline = aioredis.from_url(url, encoding="utf-8", decode_responses=True)
    client = _redis_acl_client(url, username="fixture-acl-user", password="fixture-acl-secret")
    try:
        actual = client.connection_pool.connection_kwargs
        assert actual["username"] == "fixture-acl-user"
        assert actual["password"] == "fixture-acl-secret"
        actual_options = {k: v for k, v in actual.items() if k not in {"username", "password"}}
        baseline_options = {
            k: v
            for k, v in baseline.connection_pool.connection_kwargs.items()
            if k not in {"username", "password"}
        }
        assert _comparable(actual_options) == _comparable(baseline_options)
        assert client.connection_pool.connection_class is baseline.connection_pool.connection_class
        assert client.connection_pool.max_connections == baseline.connection_pool.max_connections
        assert client.auto_close_connection_pool is True
    finally:

        async def close_disconnected_clients():
            await client.aclose()
            await baseline.aclose()

        asyncio.run(close_disconnected_clients())
