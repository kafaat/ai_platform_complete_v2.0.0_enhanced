"""C-02 — عطلُ Redis أثناء التشغيل لا يُعيد صلاحية توكنٍ مُبطَل في الإنتاج.

**العطل (مقيسٌ على main@bee67095f):** ``core/jwt_denylist.is_token_revoked`` و
``is_token_below_floor`` تُرجِعان False عند أيّ استثناء من Redis، و``api.main.get_current_user``
يقبل التوكن على هذه النتيجة. الإنتاجُ يرفض الإقلاع بلا Redis (#408)، لكنّ انقطاعه **بعد** الإقلاع
كان يجعل توكنات مستخدمٍ عُطِّل وأُبطِلت جلساته (``services/auth/main.py``) مقبولةً بـ200.

**السياسة المُثبَّتة هنا:**
- الإنتاج (``SAHOOL_ENV=production``): تعذّرُ التحقّق ⇒ 503 ``token_revocation_unverifiable``
  لكلّ الأفعال (POST/PUT/PATCH/DELETE **والقراءة**)، إذ لا قرار في الشجرة يختار التوفّر للقراءة.
- خارج الإنتاج: السلوك السابق (يُسمَح) مع تحذير.
- Redis سليم: مُبطَل ⇒ 401، سليم ⇒ 200.

Redis «الساقط» هنا عميلٌ يرمي ``redis.exceptions.ConnectionError`` كما يرمي redis-py حين لا يُجيب
الخادم، وعميلُ redis-py حقيقيّ على منفذٍ لا يستمع عليه أحد. الإثباتُ على redis-server حقيقيّ في
``test_jwt_revocation_same_redis.py`` (integration).
"""

from __future__ import annotations

import logging
import socket
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"


@pytest.fixture(scope="module")
def m():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    pytest.importorskip("fastapi")
    import api.main as main_mod

    return main_mod


class _RedisDown:
    """عميل Redis متزامن كلُّ أمرٍ فيه يرمي ConnectionError (الخادم لا يُجيب)."""

    def _down(self, *_a, **_k):
        import redis

        raise redis.exceptions.ConnectionError("Error 111 connecting to sahool-redis-state:6379")

    exists = get = setex = ping = _down


def _user(m, sub="u-disabled"):
    return m.UserSchema(user_id=sub, tenant_id="t1", role=m._normalize_role("farmer"), name_ar="م")


def _jti(token: str) -> str:
    import jwt as pyjwt

    return pyjwt.decode(token, options={"verify_signature": False})["jti"]


def _disable_and_revoke(backend, token: str, sub: str) -> None:
    """ما يفعله auth عند تعطيل المستخدم: أرضيّةُ «كلّ الجلسات» + إبطالُ jti الجلسة."""
    backend.set_token_floor(sub, int(time.time()) + 1)
    backend.revoke(_jti(token), 3600)


@pytest.fixture
def app(m):
    """تطبيقٌ صغير بالتبعيّة الحقيقيّة ``api.main.get_current_user`` على كلّ فعل."""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    a = FastAPI()

    def _ok(user=Depends(m.get_current_user)):
        return {"user_id": user.user_id}

    for method in ("get", "post", "put", "patch", "delete"):
        getattr(a, method)("/thing")(_ok)
    return TestClient(a)


def _call(app, method: str, token: str):
    return app.request(method, "/thing", headers={"Authorization": f"Bearer {token}"})


WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


@pytest.mark.parametrize("method", WRITE_METHODS)
def test_production_redis_down_revoked_token_gets_503_not_200(m, app, monkeypatch, method):
    from core.jwt_denylist import InMemoryDenylist, RedisDenylist

    monkeypatch.setenv("SAHOOL_ENV", "production")
    sub = "u-disabled"
    token = m.create_token(_user(m, sub))
    _disable_and_revoke(InMemoryDenylist(), token, sub)  # كُتِب الإبطال قبل الانقطاع
    monkeypatch.setattr(m, "_DENYLIST", RedisDenylist(_RedisDown()))

    r = _call(app, method, token)
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["code"] == "token_revocation_unverifiable"


def test_production_redis_down_reads_also_fail_closed(m, app, monkeypatch):
    """القرار: القراءة أيضاً fail-closed في الإنتاج (لا اختيار مُوثَّق للتوفّر للقراءة)."""
    from core.jwt_denylist import RedisDenylist

    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.setattr(m, "_DENYLIST", RedisDenylist(_RedisDown()))
    token = m.create_token(_user(m))
    r = _call(app, "GET", token)
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "token_revocation_unverifiable"


def test_production_real_redis_client_on_a_dead_port_gets_503(m, app, monkeypatch):
    """عميل redis-py الحقيقيّ (بنّاء الإنتاج نفسه) على منفذ لا يستمع عليه شيء ⇒ 503."""
    import redis
    from core.jwt_denylist import RedisDenylist

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    client = redis.from_url(
        f"redis://127.0.0.1:{port}/0", socket_connect_timeout=0.5, socket_timeout=0.5
    )
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.setattr(m, "_DENYLIST", RedisDenylist(client))
    r = _call(app, "POST", m.create_token(_user(m)))
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "token_revocation_unverifiable"


@pytest.mark.parametrize("env", ["production", "development"])
def test_redis_healthy_revoked_token_gets_401(m, app, monkeypatch, env):
    from core.jwt_denylist import InMemoryDenylist

    monkeypatch.setenv("SAHOOL_ENV", env)
    backend = InMemoryDenylist()
    monkeypatch.setattr(m, "_DENYLIST", backend)
    sub = "u-disabled"
    token = m.create_token(_user(m, sub))
    assert _call(app, "POST", token).status_code == 200
    _disable_and_revoke(backend, token, sub)
    assert _call(app, "POST", token).status_code == 401


@pytest.mark.parametrize("env", ["production", "development"])
def test_redis_healthy_not_revoked_gets_200(m, app, monkeypatch, env):
    from core.jwt_denylist import InMemoryDenylist

    monkeypatch.setenv("SAHOOL_ENV", env)
    monkeypatch.setattr(m, "_DENYLIST", InMemoryDenylist())
    r = _call(app, "POST", m.create_token(_user(m, "u-ok")))
    assert r.status_code == 200
    assert r.json() == {"user_id": "u-ok"}


@pytest.mark.parametrize("env", ["development", "staging", ""])
def test_non_production_redis_down_keeps_old_behaviour_with_warning(
    m, app, monkeypatch, caplog, env
):
    from core.jwt_denylist import RedisDenylist

    monkeypatch.setenv("SAHOOL_ENV", env)
    monkeypatch.setattr(m, "_DENYLIST", RedisDenylist(_RedisDown()))
    with caplog.at_level(logging.WARNING):
        r = _call(app, "POST", m.create_token(_user(m)))
    assert r.status_code == 200
    assert any("unverifiable" in rec.getMessage() for rec in caplog.records)


def test_one_check_proving_revocation_wins_over_the_other_failing(m, monkeypatch):
    """jti مُبطَل وفحص الأرضيّة يرمي ⇒ 401 لا 503 (الإثبات يغلب التعذّر) في كلّ بيئة."""
    from core.jwt_denylist import InMemoryDenylist
    from fastapi import HTTPException

    class _FloorDown(InMemoryDenylist):
        def token_floor(self, sub):
            raise ConnectionError("redis down")

    backend = _FloorDown()
    monkeypatch.setattr(m, "_DENYLIST", backend)
    token = m.create_token(_user(m))
    backend.revoke(_jti(token), 60)
    for env in ("production", "development"):
        monkeypatch.setenv("SAHOOL_ENV", env)
        with pytest.raises(HTTPException) as exc:
            m.get_current_user("Bearer " + token)
        assert exc.value.status_code == 401


def test_revocation_status_contract():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    from core.jwt_denylist import (
        REVOCATION_OK,
        REVOCATION_REVOKED,
        REVOCATION_UNVERIFIABLE,
        InMemoryDenylist,
        RedisDenylist,
        revocation_status,
    )

    down = RedisDenylist(_RedisDown())
    payload = {"jti": "j1", "sub": "u1", "iat": 1}
    assert revocation_status(down, payload) == REVOCATION_UNVERIFIABLE
    assert revocation_status(None, payload) == REVOCATION_OK  # الميزة غير مُفعَّلة
    assert revocation_status(down, {}) == REVOCATION_OK  # لا jti ولا sub/iat: لا شيء يُفحَص
    mem = InMemoryDenylist()
    assert revocation_status(mem, payload) == REVOCATION_OK
    mem.set_token_floor("u1", 2)
    assert revocation_status(mem, payload) == REVOCATION_REVOKED
