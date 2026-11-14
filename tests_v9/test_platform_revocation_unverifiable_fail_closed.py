"""C-02 — عطلُ Redis أثناء التشغيل لا يُعيد صلاحية توكنٍ مُبطَل في الإنتاج.

**العطل (مقيسٌ على main@bee67095f):** ``core/jwt_denylist.is_token_revoked`` و
``is_token_below_floor`` تُرجِعان False عند أيّ استثناء من Redis، و``api.main.get_current_user``
يقبل التوكن على هذه النتيجة. الإنتاجُ يرفض الإقلاع بلا Redis (#408)، لكنّ انقطاعه **بعد** الإقلاع
كان يجعل توكنات مستخدمٍ عُطِّل وأُبطِلت جلساته (``services/auth/main.py``) مقبولةً بـ200.

**السياسة المُثبَّتة هنا:**
- الإنتاج (``SAHOOL_ENV=production``): تعذّرُ التحقّق ⇒ 503 ``token_revocation_unverifiable``
  للأفعال غير الآمنة (POST/PUT/PATCH/DELETE) ولمستدعٍ مباشر بلا طلب.
- **قرار المالك (2026-11-14) يغيّر سياسة القراءة:** كانت القراءة أيضاً 503 في الإنتاج «إذ لا قرار
  في الشجرة يختار التوفّر للقراءة»؛ القرار صار موجوداً، فالفعل الآمن (GET/HEAD/OPTIONS) يمضي في
  كلّ بيئة مع WARNING يحمل ``REVOCATION-STORE-UNAVAILABLE-READ-ALLOWED``. الاختبار الذي كان يُثبِت
  503 للقراءة استُبدِل صراحةً بـ``test_redis_down_safe_methods_are_allowed_with_reason_in_every_env``.
- خارج الإنتاج: السلوك السابق (يُسمَح) مع تحذير.
- مُبطَلٌ مُثبَت ⇒ 401 لكلّ فعل، وإن تعذّر أحد الفحصين. Redis سليم وغير مُبطَل ⇒ 200.

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

    for method in ("get", "head", "options", "post", "put", "patch", "delete"):
        getattr(a, method)("/thing")(_ok)
    return TestClient(a)


def _call(app, method: str, token: str):
    return app.request(method, "/thing", headers={"Authorization": f"Bearer {token}"})


WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
ALL_METHODS = SAFE_METHODS + WRITE_METHODS
REASON = "REVOCATION-STORE-UNAVAILABLE-READ-ALLOWED"


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


@pytest.mark.parametrize("env", ["production", "development"])
@pytest.mark.parametrize("method", SAFE_METHODS)
def test_redis_down_safe_methods_are_allowed_with_reason_in_every_env(
    m, app, monkeypatch, caplog, method, env
):
    """قرار المالك (2026-11-14): القراءة الآمنة تمرّ أثناء انقطاع المخزن، بتحذير يحمل رمز السبب.

    يحلّ محلّ ``test_production_redis_down_reads_also_fail_closed`` الذي أثبت 503 للقراءة.
    """
    from core.jwt_denylist import RedisDenylist

    monkeypatch.setenv("SAHOOL_ENV", env)
    monkeypatch.setattr(m, "_DENYLIST", RedisDenylist(_RedisDown()))
    with caplog.at_level(logging.WARNING, logger="sahool.jwt_denylist"):
        r = _call(app, method, m.create_token(_user(m, "u-read")))
    assert r.status_code == 200, r.text
    if method != "HEAD":
        assert r.json() == {"user_id": "u-read"}
    assert any(REASON in rec.getMessage() and method in rec.getMessage() for rec in caplog.records)


def test_production_redis_down_direct_call_without_request_is_refused(m, monkeypatch):
    """مستدعٍ مباشر بلا طلب (مصافحة WebSocket مثلاً) لا فعل له ⇒ لا يُعامَل قراءةً ⇒ 503."""
    from core.jwt_denylist import RedisDenylist
    from fastapi import HTTPException

    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.setattr(m, "_DENYLIST", RedisDenylist(_RedisDown()))
    with pytest.raises(HTTPException) as exc:
        m.get_current_user("Bearer " + m.create_token(_user(m)))
    assert exc.value.status_code == 503


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


@pytest.mark.parametrize("method", ALL_METHODS)
@pytest.mark.parametrize("env", ["production", "development"])
def test_redis_healthy_revoked_token_gets_401(m, app, monkeypatch, env, method):
    from core.jwt_denylist import InMemoryDenylist

    monkeypatch.setenv("SAHOOL_ENV", env)
    backend = InMemoryDenylist()
    monkeypatch.setattr(m, "_DENYLIST", backend)
    sub = "u-disabled"
    token = m.create_token(_user(m, sub))
    assert _call(app, method, token).status_code == 200
    _disable_and_revoke(backend, token, sub)
    assert _call(app, method, token).status_code == 401


@pytest.mark.parametrize("method", ALL_METHODS)
@pytest.mark.parametrize("env", ["production", "development"])
def test_proven_revocation_is_401_for_every_method_while_the_other_check_fails(
    m, app, monkeypatch, env, method
):
    """jti مُبطَل وفحص الأرضيّة يرمي ⇒ 401 لكلّ فعل، القراءة ضمناً: الإثبات يغلب السماح بالقراءة."""
    from core.jwt_denylist import InMemoryDenylist

    class _FloorDown(InMemoryDenylist):
        def token_floor(self, sub):
            raise ConnectionError("redis down")

    monkeypatch.setenv("SAHOOL_ENV", env)
    backend = _FloorDown()
    monkeypatch.setattr(m, "_DENYLIST", backend)
    token = m.create_token(_user(m))
    backend.revoke(_jti(token), 60)
    assert _call(app, method, token).status_code == 401


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


def test_unverifiable_allows_contract():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    from core.jwt_denylist import READ_ALLOWED_REASON, unverifiable_allows

    assert READ_ALLOWED_REASON == REASON
    for production in (True, False):
        for verb in ("GET", "head", "OPTIONS"):
            assert unverifiable_allows(verb, production=production) is True
    for verb in (*WRITE_METHODS, None, "", "TRACE"):
        assert unverifiable_allows(verb, production=True) is False
        assert unverifiable_allows(verb, production=False) is True  # C-02 خارج الإنتاج


# ─── المسارات الصارمة (مراجعة #1449): GET مُبوَّب بصلاحية غير عرض أو بأثر جانبيّ ─────────


def _role_user(m, role: str, sub: str = "u-strict"):
    return m.UserSchema(user_id=sub, tenant_id="t1", role=m._normalize_role(role), name_ar="م")


@pytest.fixture
def perm_app(m):
    """GET تحت ثلاث تبعيّات: صلاحية عرض، صلاحية إدارة منصّة، وصلاحية عرض معلَنة صارمة."""
    from core.authorization import Permission
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    a = FastAPI()
    deps = {
        "/view": m.require_permission(Permission.FIELD_VIEW),
        "/platform": m.require_permission(Permission.PLATFORM_MANAGE),
        "/view-strict": m.require_permission(Permission.FIELD_VIEW, strict_revocation=True),
    }
    for path, dep in deps.items():

        def _ok(user=Depends(dep)):
            return {"user_id": user.user_id}

        a.get(path)(_ok)
    return TestClient(a)


@pytest.mark.parametrize(
    ("path", "role", "prod_status"),
    [("/view", "owner", 200), ("/platform", "platform_admin", 503), ("/view-strict", "owner", 503)],
)
def test_strict_routes_fail_closed_on_get_in_production(
    m, perm_app, monkeypatch, path, role, prod_status
):
    from core.jwt_denylist import RedisDenylist

    monkeypatch.setattr(m, "_DENYLIST", RedisDenylist(_RedisDown()))
    token = m.create_token(_role_user(m, role))
    monkeypatch.setenv("SAHOOL_ENV", "production")
    r = perm_app.get(path, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == prod_status, r.text
    if prod_status == 503:
        assert r.json()["detail"]["code"] == "token_revocation_unverifiable"
    monkeypatch.setenv("SAHOOL_ENV", "development")  # C-02 خارج الإنتاج: يُسمَح كما كان
    assert perm_app.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 200


@pytest.mark.parametrize("path", ["/view", "/platform", "/view-strict"])
def test_strict_routes_pass_with_a_healthy_store(m, perm_app, monkeypatch, path):
    from core.jwt_denylist import InMemoryDenylist

    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.setattr(m, "_DENYLIST", InMemoryDenylist())
    token = m.create_token(_role_user(m, "platform_admin" if path == "/platform" else "owner"))
    assert perm_app.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 200


@pytest.mark.parametrize(
    ("path", "role"),
    [
        # break-glass: PLATFORM_MANAGE، يقرأ مستأجِراً آخر ويحدّث access_count.
        ("/api/v1/admin/break-glass/tok-1/fields", "platform_admin"),
        # تصدير ISOXML: يفحص EQUIPMENT_MANAGE ويُدرِج machinery_export_artifacts.
        ("/api/v1/fields/f-1/prescriptions/p-1/export?format=isoxml", "owner"),
    ],
)
def test_the_reviewed_side_effect_gets_fail_closed_in_production(m, monkeypatch, path, role):
    """المساران اللذان سمّتهما مراجعة #1449، على تطبيق المنصّة الحقيقيّ: 503 قبل أيّ عمل."""
    from core.jwt_denylist import RedisDenylist
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.setattr(m, "_DENYLIST", RedisDenylist(_RedisDown()))
    token = m.create_token(_role_user(m, role))
    r = TestClient(m.app, raise_server_exceptions=False).get(
        path, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["code"] == "token_revocation_unverifiable"


def test_strict_revocation_rule():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    from core.authorization import Permission
    from core.jwt_denylist import strict_revocation_for

    for p in Permission:
        assert strict_revocation_for(p.value) is (not p.value.endswith(":view")), p
    assert strict_revocation_for(Permission.PLATFORM_MANAGE.value)
    assert strict_revocation_for(Permission.EQUIPMENT_MANAGE.value)
    assert not strict_revocation_for(Permission.FIELD_VIEW.value)
