"""AUTH-REDIS-ACL-FIXTURE-CREDENTIAL-PRECEDENCE-01: exercise the real URL parser.

Only disconnected clients are constructed; these unit cases need no Redis or PG.
The live fixture separately proves authentication, reads and actual SETEX denial.
"""

import asyncio

import pytest
import redis.asyncio as aioredis

from tests_v9.test_auth_admin_authz_live_pg_redis import _redis_acl_client

pytestmark = pytest.mark.unit


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
        assert actual_options == baseline_options
        assert client.connection_pool.connection_class is baseline.connection_pool.connection_class
        assert client.connection_pool.max_connections == baseline.connection_pool.max_connections
        assert client.auto_close_connection_pool is True
    finally:

        async def close_disconnected_clients():
            await client.aclose()
            await baseline.aclose()

        asyncio.run(close_disconnected_clients())
