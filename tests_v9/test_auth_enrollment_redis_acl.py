"""Enrollment capabilities use auth's narrow Redis ACL, never a broad MFA grant."""

import pytest

from tests_v9.test_redis_acl_per_service import (
    _argv,
    _live_required,
    _login,
    _matrix,
    _password_for,
    _redis_server_bin,
    _running_server,
    _user_rules,
)


@pytest.mark.unit
def test_enrollment_keys_are_granted_only_to_auth():
    key = "sahool:mfa:enrollment:*"
    users = _matrix()["servers"]["sahool-redis-state"]["users"]
    assert key in users["sahool-auth"]["keys"]
    rules = _user_rules(_argv("sahool-redis-state"))
    assert "~" + key in rules["sahool-auth"]
    assert "~sahool:mfa:*" not in rules["sahool-auth"]
    assert {"get", "setex", "getdel"} <= set(users["sahool-auth"]["commands"])
    for name, user in users.items():
        if name != "sahool-auth":
            assert key not in user["keys"]


@pytest.mark.integration
def test_live_auth_enrollment_roundtrip_and_cross_namespace_denial(tmp_path):
    redis = pytest.importorskip("redis")
    binary = _redis_server_bin()
    if not binary:
        if _live_required():
            pytest.fail("REDIS_ACL_LIVE_REQUIRED=1 requires redis-server")
        pytest.skip("redis-server unavailable")
    users = _matrix()["servers"]["sahool-redis-state"]["users"]
    with _running_server(binary, "sahool-redis-state", tmp_path) as (port, _admin):
        with _login(
            port, "sahool-auth", _password_for(users["sahool-auth"]["password_env"])
        ) as auth:
            key = "sahool:mfa:enrollment:review-proof"
            assert auth.setex(key, 300, "digest")
            assert auth.get(key) == "digest"
            assert auth.getdel(key) == "digest"
            assert auth.getdel(key) is None
            for other in ("sahool:mfa:other:proof", "sahool:outside:proof"):
                with pytest.raises(redis.exceptions.NoPermissionError):
                    auth.setex(other, 300, "denied")
        name = "sahool-platform-denylist"
        with _login(port, name, _password_for(users[name]["password_env"])) as platform:
            with pytest.raises(redis.exceptions.NoPermissionError):
                platform.get(key)
