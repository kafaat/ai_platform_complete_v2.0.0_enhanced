"""RASTER-CACHE-INVALIDATION-WORKER-HAS-NO-REDIS-URL-01 regression."""

import pytest

from tests_v9.test_redis_acl_per_service import (
    _compose,
    _env,
    _live_required,
    _matrix,
    _redis_server_bin,
    _running_server,
)

WORKER = "sahool-raster-cache-invalidation-worker"
CHANNEL = "raster:layer_evict"
pytestmark = pytest.mark.unit


def test_worker_has_own_publish_only_identity():
    user = _matrix()["servers"]["sahool-redis"]["users"][WORKER]
    assert user["commands"] == ["ping", "publish"]
    assert user["keys"] == []
    assert user["channels"] == [CHANNEL]
    from tests_v9.test_redis_acl_per_service import _password_for

    url = _env(_compose()["services"][WORKER])["REDIS_URL"]
    assert url == f"redis://{WORKER}:{_password_for(user['password_env'])}@sahool-redis:6379/0"


@pytest.mark.integration
def test_live_compose_publisher_reaches_subscriber_and_denies_other_access(tmp_path):
    import redis

    binary = _redis_server_bin()
    if not binary:
        if _live_required():
            pytest.fail("REDIS_ACL_LIVE_REQUIRED=1 requires redis-server")
        pytest.skip("redis-server unavailable")
    with _running_server(binary, "sahool-redis", tmp_path) as (port, _admin):
        services = _compose()["services"]

        def client(service):
            url = _env(services[service])["REDIS_URL"]
            return redis.Redis.from_url(
                url.replace("sahool-redis:6379", f"127.0.0.1:{port}"), decode_responses=True
            )

        with client(WORKER) as publisher, client("sahool-raster-service") as subscriber:
            with subscriber.pubsub() as messages:
                messages.subscribe(CHANNEL)
                assert messages.get_message(timeout=3)["type"] == "subscribe"
                assert publisher.publish(CHANNEL, "field-regression") == 1
                received = messages.get_message(timeout=3)
                assert received["channel"] == CHANNEL
                assert received["data"] == "field-regression"
            for command in (
                ("GET", "stac:test"),
                ("SET", "anything", "x"),
                ("PUBLISH", "other", "x"),
                ("SUBSCRIBE", CHANNEL),
                ("FLUSHALL",),
            ):
                with pytest.raises(redis.exceptions.NoPermissionError):
                    publisher.execute_command(*command)
