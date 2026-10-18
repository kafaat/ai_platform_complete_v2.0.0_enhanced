"""PLATFORM-IGNORES-AUTH-REVOKE-ALL-SESSIONS-FLOOR-01 — المنصّة تحترم أرضيّةَ «إبطال كلّ الجلسات».

**العطل:** auth يُبطل كلّ جلسات المستخدم عند تغيير كلمة المرور أو إعادتها أو الدور أو التعطيل
(``revoke_all_user_sessions``، ``services/auth/main.py``) بأرضيّةٍ ``sahool:user:token_floor:{sub}``
ويرفض كلّ توكن ``iat`` فيه أقدم منها. المنصّة كانت تفحص ``jti`` وحده، فتوكنُ حسابٍ عُطِّل أو
غُيِّرت كلمتُه بقي مقبولاً لديها حتّى انقضائه.

**الإصلاح:** ``core/jwt_denylist.is_token_below_floor`` بقاعدة auth نفسها، يستدعيها
``get_current_user``؛ والقراءةُ على خادم auth بمستخدم ``sahool-platform-denylist`` ومحدِّدٍ
``(+get %R~sahool:user:token_floor:*)`` — قراءةٌ فقط، فالمنصّة لا تكتب أرضيّة.

① وحدة: المفتاحُ مفتاحُ auth، والقاعدةُ قاعدتُه (مقارنةً بدالّة auth الحقيقيّة)، وfail-open.
② ``get_current_user``: توكنٌ تحت الأرضيّة ⇒ 401، وبعدها ⇒ مقبول.
③ حيّ على redis-server بسطر compose: ``revoke_all_user_sessions`` الحقيقيّة في auth ⇒ 401 في
   المنصّة، والمنصّةُ تقرأ الأرضيّة ولا تكتبها.
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

import pytest
from test_auth_session_revocation import _FakeRedis, auth_mod  # noqa: F401 — fixture
from test_jwt_revocation_same_redis import (  # noqa: F401 — fixtures
    _client,
    _platform_path,
    platform_main,
    state_server,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
AUTH_MAIN = ROOT / "services" / "auth" / "main.py"


def _denylist():
    _platform_path()
    import core.jwt_denylist as m

    return m


# ── ① الوحدة ─────────────────────────────────────────────────────────────────


def test_platform_reads_the_floor_key_auth_writes():
    src = AUTH_MAIN.read_text(encoding="utf-8")
    written = set(re.findall(r'f"(sahool:user:token_floor:)\{\w+\}"', src))
    assert written == {"sahool:user:token_floor:"}, written
    assert _denylist().TOKEN_FLOOR_KEY.format(sub="42") == "sahool:user:token_floor:42"


@pytest.mark.parametrize(
    "payload,floor,expected",
    [
        ({"sub": "42", "iat": 99}, 100, True),
        ({"sub": "42", "iat": 100}, 100, False),
        ({"sub": "42", "iat": 101}, 100, False),
        ({"sub": "42", "iat": 99}, None, False),
        ({"iat": 99}, 100, False),
        ({"sub": "42"}, 100, False),
        ({"sub": 42, "iat": 99.0}, 100, True),
    ],
    ids=["below", "equal", "above", "no-floor", "no-sub", "no-iat", "int-sub-float-iat"],
)
def test_floor_rule_matches_auth(auth_mod, payload, floor, expected):  # noqa: F811
    m = _denylist()
    backend = m.InMemoryDenylist()
    fake = _FakeRedis()
    if floor is not None:
        backend.set_token_floor("42", floor)
        fake.kv["sahool:user:token_floor:42"] = str(floor)
    assert m.is_token_below_floor(backend, payload) is expected
    saved = auth_mod._redis
    auth_mod._redis = fake
    try:
        assert asyncio.run(auth_mod.is_token_below_floor(payload)) is expected, "auth يحكم بغيره"
    finally:
        auth_mod._redis = saved


def test_redis_backend_reads_bytes_and_absence():
    m = _denylist()

    class _Sync:
        def __init__(self, kv):
            self.kv = kv

        def get(self, k):
            return self.kv.get(k)

    backend = m.RedisDenylist(_Sync({"sahool:user:token_floor:7": b"500"}))
    assert backend.token_floor("7") == 500
    assert backend.token_floor("8") is None
    assert m.is_token_below_floor(backend, {"sub": "7", "iat": 499}) is True


def test_floor_check_fails_open_like_the_jti_check():
    m = _denylist()

    class _Broken:
        def token_floor(self, sub):
            raise ConnectionError("redis down")

    class _NoFloors:
        def is_revoked(self, jti):
            return False

    assert m.is_token_below_floor(_Broken(), {"sub": "1", "iat": 1}) is False
    assert m.is_token_below_floor(_NoFloors(), {"sub": "1", "iat": 1}) is False
    assert m.is_token_below_floor(None, {"sub": "1", "iat": 1}) is False


# ── ② get_current_user ─────────────────────────────────────────────────────


def _user(platform_main, sub="u-floor"):  # noqa: F811
    return platform_main.UserSchema(
        user_id=sub, tenant_id="t1", role=platform_main._normalize_role("farmer"), name_ar="م"
    )


def test_get_current_user_rejects_a_token_issued_before_the_floor(platform_main, monkeypatch):  # noqa: F811
    from fastapi import HTTPException

    backend = _denylist().InMemoryDenylist()
    monkeypatch.setattr(platform_main, "_DENYLIST", backend)
    token = platform_main.create_token(_user(platform_main))
    assert platform_main.get_current_user("Bearer " + token).user_id == "u-floor"

    backend.set_token_floor("u-floor", int(time.time()) + 1)  # ما يضعه auth (+1)
    with pytest.raises(HTTPException) as exc:
        platform_main.get_current_user("Bearer " + token)
    assert exc.value.status_code == 401

    backend.set_token_floor("u-floor", int(time.time()) - 5)  # توكنٌ صدر بعد الأرضيّة
    assert platform_main.get_current_user("Bearer " + token).user_id == "u-floor"


# ── ③ الإثباتُ الحيّ ────────────────────────────────────────────────────────


@pytest.mark.integration
def test_live_auth_revoke_all_sessions_is_401_on_the_platform(
    state_server,  # noqa: F811
    platform_main,  # noqa: F811
    auth_mod,  # noqa: F811
    monkeypatch,
):
    """``revoke_all_user_sessions`` الحقيقيّة (بمستخدم auth) ⇒ بنّاءُ المنصّة الحقيقيّ يردّ 401."""
    import redis
    import redis.asyncio as aioredis
    from fastapi import HTTPException

    _, urls, admin = state_server
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.setenv("DENYLIST_REDIS_URL", urls["services/sahool-platform"])
    monkeypatch.setenv("REDIS_URL", "redis://sahool-platform:x@127.0.0.1:1/0")  # كاشٌ لا يُجيب
    backend = platform_main._build_denylist()
    assert type(backend).__name__ == "RedisDenylist"
    monkeypatch.setattr(platform_main, "_DENYLIST", backend)

    sub = "424242"
    token = platform_main.create_token(_user(platform_main, sub))
    assert platform_main.get_current_user("Bearer " + token).user_id == sub

    async def _revoke_all():
        client = aioredis.Redis.from_url(urls["services/auth"])
        monkeypatch.setattr(auth_mod, "_redis", client)
        try:
            await auth_mod.revoke_all_user_sessions(int(sub))
        finally:
            await client.aclose()

    asyncio.run(_revoke_all())
    floor = int(admin.get(f"sahool:user:token_floor:{sub}"))
    with pytest.raises(HTTPException) as exc:
        platform_main.get_current_user("Bearer " + token)
    assert exc.value.status_code == 401

    while int(time.time()) < floor:  # توكنٌ يصدر بعد الأرضيّة يُقبَل (≤ ثانيتان)
        time.sleep(0.1)
    fresh = platform_main.create_token(_user(platform_main, sub))
    assert platform_main.get_current_user("Bearer " + fresh).user_id == sub

    platform = _client(urls["services/sahool-platform"])
    try:
        assert int(platform.get(f"sahool:user:token_floor:{sub}")) == floor
        for cmd in (
            ("SETEX", f"sahool:user:token_floor:{sub}", "60", "1"),
            ("SET", f"sahool:user:token_floor:{sub}", "1"),
            ("DEL", f"sahool:user:token_floor:{sub}"),
            ("EXPIRE", f"sahool:user:token_floor:{sub}", "1"),
            ("GET", f"sahool:user:token_floor_other:{sub}"),
        ):
            with pytest.raises(redis.exceptions.NoPermissionError):
                platform.execute_command(*cmd)
        assert int(admin.get(f"sahool:user:token_floor:{sub}")) == floor, "الأرضيّةُ تغيّرت"
    finally:
        platform.close()
