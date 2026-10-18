"""إبطالُ JWT يُكتَب ويُقرأ على خادم Redis واحد — ``JWT-REVOCATION-WRITTEN-AND-READ-ON-DIFFERENT-REDIS-SERVERS-01``.

**العطلُ (مقيسٌ نصّيّاً على main@f3936a771):** auth يكتب ``sahool:jti:revoked:{jti}``
(``services/auth/main.py:641``) على ``REDIS_URL`` الخاصّ به، وهو في ``docker-compose.v9.yml``
``sahool-redis-state``. والمنصّة تقرأ المفتاحَ نفسَه (``_build_denylist`` ⇒ ``RedisDenylist``) من
``REDIS_URL`` الخاصّ بها، وهو ``sahool-redis`` — الكاش. فتوكنٌ أُبطِل عند الخروج من auth يبقى مقبولاً
لدى المنصّة حتّى انقضائه، وخروجُ المنصّة (``POST /api/v1/auth/logout``) يُبطِل على الكاش فلا يراه auth.

**الإصلاح:** ``core/jwt_denylist.denylist_redis_url`` — ``DENYLIST_REDIS_URL`` إن ضُبط، وإلّا
``REDIS_URL`` حرفيّاً كما كان (فكلُّ نشرٍ لم يضبطه، ومنه Railway، يتصرّف كما قبل). compose يضبطه
للمنصّة على خادم auth بمستخدم ACL لا يملك إلّا ``PING``/``EXISTS``/``SETEX`` على ``sahool:jti:revoked:*``.

ثلاث طبقات:
① ``unit``: البنّاءُ نفسُه (``api.main._build_denylist``) يُفضِّل ``DENYLIST_REDIS_URL`` ويرجع إلى
   ``REDIS_URL`` حين يغيب، ورفضُ الإقلاع في الإنتاج بلا Redis باقٍ.
② ``unit``: عقدُ compose — كلُّ خدمةٍ تفحص الإبطال (مشتقّةً من الشيفرة: من يذكر المفتاح، ومن
   compose: من يُشغِّل صورتَها بأمرها الافتراضيّ) تبلغه على **الخادم والقاعدة نفسيهما**، وذلك الخادمُ
   ``noeviction`` (الكاشُ ``allkeys-lru`` يطرد الإبطالات تحت الضغط).
③ ``integration``: خادمُ الحالة بسطر أمر compose حرفيّاً: auth يكتب، ومستخدمُ المنصّة يرى
   (``EXISTS`` ⇒ 1) ويُرَدّ ``NOPERM`` على ``SET``/``DEL``/``FLUSHALL``/مفاتيح غيره؛ ثمّ بنّاءُ المنصّة
   الحقيقيّ برابط compose يرفض توكناً أبطله auth بـ401، وخروجُ المنصّة يراه auth.
"""

from __future__ import annotations

import contextlib
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from redis.connection import parse_url
from test_redis_acl_per_service import (
    _compose,
    _env,
    _live_required,
    _matrix,
    _redis_server_bin,
    _running_server,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
AUTH_MAIN = ROOT / "services" / "auth" / "main.py"
REVOKED_PREFIX = "sahool:jti:revoked:"
#: أين يبحث الاشتقاقُ عن فاحصي الإبطال (كلُّ شيفرةٍ تُشحَن في صورة خدمة).
CODE_ROOTS = ("services", "shared", "agents", "bots")


def _platform_path() -> None:
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))


def _denylist_url_fn():
    _platform_path()
    from core.jwt_denylist import denylist_redis_url

    return denylist_redis_url


def _auth_redis_url(env: dict[str, str]) -> str:
    """كما يقرؤه auth (``REDIS_URL = os.getenv("REDIS_URL", <افتراض>)``) — الافتراضُ من الملفّ لا منّا."""
    m = re.search(
        r'^REDIS_URL = os\.getenv\("REDIS_URL", "([^"]*)"\)$',
        AUTH_MAIN.read_text(encoding="utf-8"),
        re.M,
    )
    assert m, "services/auth/main.py لم يعد يقرأ REDIS_URL هكذا — حدِّث المُحلِّل أدناه"
    return env.get("REDIS_URL", m.group(1))


#: لكلّ دليل خدمةٍ يفحص الإبطال: كيف تختار رابطَ قائمته من بيئتها — بشيفرتها هي لا بنسخةٍ منها.
_RESOLVERS = {
    "services/auth": lambda env: _auth_redis_url(env),
    "services/sahool-platform": lambda env: _denylist_url_fn()(env),
}


# ── ① البنّاء ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "env,expected",
    [
        (
            {"DENYLIST_REDIS_URL": "redis://d@state:6379/0", "REDIS_URL": "redis://c@cache:6379/0"},
            "redis://d@state:6379/0",
        ),
        ({"REDIS_URL": "redis://c@cache:6379/0"}, "redis://c@cache:6379/0"),
        (
            {"DENYLIST_REDIS_URL": "", "REDIS_URL": "redis://c@cache:6379/0"},
            "redis://c@cache:6379/0",
        ),
        (
            {"DENYLIST_REDIS_URL": "  ", "REDIS_URL": "redis://c@cache:6379/0"},
            "redis://c@cache:6379/0",
        ),
        ({}, ""),
    ],
    ids=[
        "prefers-denylist-url",
        "unset-falls-back",
        "empty-falls-back",
        "blank-falls-back",
        "neither",
    ],
)
def test_denylist_url_prefers_its_own_variable_and_falls_back_to_redis_url(env, expected):
    assert _denylist_url_fn()(env) == expected


@pytest.fixture(scope="module")
def platform_main():
    _platform_path()
    pytest.importorskip("fastapi")
    import api.main as main_mod

    return main_mod


class _FakeRedisModule:
    """بديلُ وحدة ``redis`` يسجّل الرابط الذي يبني به البنّاءُ عميلَه."""

    def __init__(self, ping_ok: bool = True):
        self.urls: list[str] = []
        self._ping_ok = ping_ok

    def from_url(self, url, **_kw):
        self.urls.append(url)
        outer = self

        class _Client:
            def ping(self):
                if not outer._ping_ok:
                    raise ConnectionError("unreachable")
                return True

            def exists(self, _key):
                return 0

        return _Client()


@pytest.mark.parametrize(
    "env,expected_url",
    [
        (
            {
                "DENYLIST_REDIS_URL": "redis://d:pw@state:6379/0",
                "REDIS_URL": "redis://c:pw@cache:6379/0",
            },
            "redis://d:pw@state:6379/0",
        ),
        ({"REDIS_URL": "redis://c:pw@cache:6379/0"}, "redis://c:pw@cache:6379/0"),
        (
            {"DENYLIST_REDIS_URL": "", "REDIS_URL": "redis://c:pw@cache:6379/0"},
            "redis://c:pw@cache:6379/0",
        ),
    ],
    ids=["denylist-url-wins", "unset-uses-redis-url", "empty-uses-redis-url"],
)
def test_platform_denylist_builder_connects_to_the_selected_url(
    platform_main, monkeypatch, env, expected_url
):
    fake = _FakeRedisModule()
    monkeypatch.setitem(sys.modules, "redis", fake)
    for var in ("DENYLIST_REDIS_URL", "REDIS_URL"):
        monkeypatch.delenv(var, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    backend = platform_main._build_denylist()
    assert fake.urls == [expected_url], (
        f"بنّاءُ قائمة الإبطال اتّصل بـ{fake.urls} والمتوقَّع {expected_url} — "
        "DENYLIST_REDIS_URL (خادمُ auth) يتقدّم على REDIS_URL (الكاش)، وغيابُه يُبقي REDIS_URL كما كان."
    )
    assert type(backend).__name__ == "RedisDenylist"


def test_platform_denylist_still_refuses_to_start_in_production_without_redis(
    platform_main, monkeypatch
):
    """رفضُ الإقلاع (حوكمة #408) باقٍ: لا رابطَ أصلاً، أو رابطُ القائمة لا يُجيب ⇒ RuntimeError."""
    monkeypatch.setenv("SAHOOL_ENV", "production")
    for var in ("DENYLIST_REDIS_URL", "REDIS_URL"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="Redis"):
        platform_main._build_denylist()
    monkeypatch.setitem(sys.modules, "redis", _FakeRedisModule(ping_ok=False))
    monkeypatch.setenv("DENYLIST_REDIS_URL", "redis://d:pw@state:6379/0")
    monkeypatch.setenv("REDIS_URL", "redis://c:pw@cache:6379/0")
    with pytest.raises(RuntimeError, match="Redis"):
        platform_main._build_denylist()


# ── ② عقدُ compose ──────────────────────────────────────────────────────────────


def _checker_dirs() -> set[str]:
    """أدلّةُ الخدمات التي تذكر شيفرتُها (لا اختباراتُها) مفتاحَ الإبطال."""
    found: set[str] = set()
    for top in CODE_ROOTS:
        for f in (ROOT / top).rglob("*.py"):
            rel = f.relative_to(ROOT)
            if any(p in {"tests", "test", "__pycache__"} for p in rel.parts) or f.name.startswith(
                "test_"
            ):
                continue
            if REVOKED_PREFIX in f.read_text(encoding="utf-8", errors="replace"):
                found.add("/".join(rel.parts[:2]) if top == "services" else top)
    return found


def _dockerfile(svc: dict) -> str:
    build = svc.get("build")
    return str(build.get("dockerfile", "")) if isinstance(build, dict) else ""


def _checkers() -> list[tuple[str, str, str]]:
    """(خدمةُ compose، دليلُ شيفرتها، رابطُ قائمتها) لكلّ خدمةٍ تُشغِّل صورةَ فاحصٍ بأمرها الافتراضيّ.

    خدماتٌ تبني صورةَ المنصّة بأمرٍ آخر (``python -m api.phase_runtime_workers …``) عمّالٌ لا
    يستوردون ``api.main`` فلا يفحصون توكناً؛ أمرُ الصورة الافتراضيّ (``uvicorn api.main:app``/
    ``main:app``) هو الذي يبني القائمة ويفحصها.
    """
    rows = []
    for name, svc in _compose()["services"].items():
        if not isinstance(svc, dict) or svc.get("command"):
            continue
        for d in _RESOLVERS:
            if _dockerfile(svc).startswith(f"{d}/"):
                rows.append((name, d, _RESOLVERS[d](_env(svc))))
    return rows


def _redis_server_of(host: str) -> dict:
    svc = _compose()["services"].get(host)
    assert isinstance(svc, dict) and "redis" in str(svc.get("image", "")), (
        f"{host} ليس خادمَ Redis في compose"
    )
    return svc


def test_every_revocation_checker_is_classified():
    """فاحصٌ جديد (أو المفتاحُ في shared/) يحتاج أن يُقال كيف يختار رابطَه — لا أن يُفترَض."""
    dirs = _checker_dirs()
    assert dirs == set(_RESOLVERS), (
        f"أدلّةٌ تذكر {REVOKED_PREFIX}* {sorted(dirs)} ≠ المُصنَّفة {sorted(_RESOLVERS)} — "
        "أضِف لكلّ فاحصٍ جديد كيف يختار رابطَ قائمته في _RESOLVERS واحكم عقدَه أدناه."
    )


def test_every_revocation_checker_reads_the_redis_server_and_db_auth_writes():
    rows = _checkers()
    services = {name for name, _, _ in rows}
    assert {d for _, d, _ in rows} == set(_RESOLVERS) and len(rows) >= 2, (
        f"لم يُعثَر على خدمة compose لكلّ فاحص: {rows}"
    )
    targets = {}
    for name, _, url in rows:
        assert url, f"{name}: لا رابطَ Redis لقائمة الإبطال — الإبطالُ داخل العمليّة وحدَها"
        p = parse_url(url)
        targets[name] = (p.get("host"), p.get("port", 6379), int(p.get("db", 0) or 0))
    assert len(set(targets.values())) == 1, (
        "قائمةُ إبطال JWT تُكتَب وتُقرأ على خوادم مختلفة — توكنٌ أُبطِل لدى خدمةٍ يبقى مقبولاً لدى "
        f"أخرى حتّى انقضائه: {targets}"
    )
    host, _, _ = next(iter(targets.values()))
    command = str(_redis_server_of(host).get("command"))
    assert "--maxmemory-policy noeviction" in command, (
        f"{host} يطرد المفاتيح ({command[:80]}…) — إبطالٌ مطرود توكنٌ مقبول من جديد"
    )
    users = _matrix()["servers"][host]["users"]
    for name, _, url in rows:
        user = parse_url(url).get("username")
        rules = users.get(user)
        assert rules and "exists" in rules["commands"] and f"{REVOKED_PREFIX}*" in rules["keys"], (
            f"{name}: المستخدم {user!r} على {host} لا يملك EXISTS على {REVOKED_PREFIX}*"
        )
    assert services, rows


def test_platform_keeps_its_cache_traffic_on_the_cache_server():
    """الإصلاحُ ينقل القائمةَ وحدَها: حدُّ المعدّل والطقس على ``REDIS_URL`` كما كانا."""
    for name, d, _ in _checkers():
        if d != "services/sahool-platform":
            continue
        env = _env(_compose()["services"][name])
        cache = parse_url(env["REDIS_URL"])
        command = str(_redis_server_of(cache["host"]).get("command"))
        assert "allkeys-lru" in command, (name, cache["host"])
        user = _matrix()["servers"][cache["host"]]["users"][cache["username"]]
        assert f"{REVOKED_PREFIX}*" not in user["keys"], (
            "مستخدمُ الكاش ما زال يملك مفاتيحَ الإبطال — القائمةُ لا تُقرأ من هناك بعد الآن"
        )
        assert {"sahool:ratelimit:*", "sahool:weather:tile:*"} <= set(user["keys"]), user["keys"]


# ── ③ الإثباتُ الحيّ ────────────────────────────────────────────────────────────


def _local(url: str, port: int) -> str:
    parts = urlsplit(url)
    userinfo = parts.netloc.rpartition("@")[0]
    return urlunsplit(parts._replace(netloc=f"{userinfo}@127.0.0.1:{port}"))


@pytest.fixture(scope="module")
def state_server(tmp_path_factory):
    """خادمُ القائمة المشترك (مشتقٌّ من compose) بسطر أمره حرفيّاً ⇒ (المنفذ، {خدمة: رابطٌ محلّيّ})."""
    pytest.importorskip("redis")
    binary = _redis_server_bin()
    if not binary:
        if _live_required():
            pytest.fail("REDIS_ACL_LIVE_REQUIRED=1 ولا redis-server (REDIS_SERVER_BIN أو PATH)")
        pytest.skip("لا redis-server — الإثباتُ الحيّ غير مقيس في هذه البيئة")
    rows = _checkers()
    hosts = {parse_url(url)["host"] for _, _, url in rows}
    if len(hosts) != 1:
        pytest.fail(f"الفاحصون على خوادم مختلفة {sorted(hosts)} — لا خادمَ مشترك يُقلَع")
    host = hosts.pop()
    with _running_server(binary, host, tmp_path_factory.mktemp(host)) as (port, admin):
        urls = {d: _local(url, port) for _, d, url in rows}
        yield port, urls, admin


def _client(url: str):
    import redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry

    return redis.Redis.from_url(url, decode_responses=True, retry=Retry(NoBackoff(), 0))


@pytest.mark.integration
def test_live_platform_denylist_user_sees_what_auth_writes_and_nothing_else(state_server):
    import redis

    _, urls, admin = state_server
    jti = uuid.uuid4().hex
    key = f"{REVOKED_PREFIX}{jti}"
    auth = _client(urls["services/auth"])
    platform = _client(urls["services/sahool-platform"])
    try:
        admin.set("sahool:refresh:live-canary", "u:t")
        auth.setex(key, 60, "1")  # ما يكتبه auth عند الخروج (services/auth/main.py:641)
        assert platform.exists(key) == 1, "المنصّة لا ترى إبطالاً كتبه auth"
        assert platform.exists(f"{REVOKED_PREFIX}{uuid.uuid4().hex}") == 0
        for cmd in (
            ("SET", key, "0"),
            ("DEL", key),
            ("GET", key),
            ("FLUSHALL",),
            ("KEYS", "*"),
            ("CONFIG", "GET", "*"),
            ("EXISTS", "sahool:refresh:live-canary"),
            ("GET", "sahool:refresh:live-canary"),
            ("SETEX", "sahool:lockout:someone", "60", "1"),
        ):
            with pytest.raises(redis.exceptions.NoPermissionError):
                platform.execute_command(*cmd)
        assert auth.exists(key) == 1, "الإبطالُ مُسِح"
        assert admin.get("sahool:refresh:live-canary") == "u:t"
    finally:
        auth.close()
        platform.close()


@pytest.mark.integration
def test_live_platform_rejects_a_token_auth_revoked_and_auth_sees_a_platform_logout(
    state_server, platform_main, monkeypatch
):
    """البنّاءُ الحقيقيّ برابط compose: إبطالُ auth ⇒ 401 في المنصّة، وخروجُ المنصّة يراه auth."""
    from fastapi import HTTPException

    _, urls, _ = state_server
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.setenv("DENYLIST_REDIS_URL", urls["services/sahool-platform"])
    monkeypatch.setenv("REDIS_URL", "redis://sahool-platform:x@127.0.0.1:1/0")  # كاشٌ لا يُجيب
    backend = platform_main._build_denylist()
    assert type(backend).__name__ == "RedisDenylist"
    monkeypatch.setattr(platform_main, "_DENYLIST", backend)

    import jwt as pyjwt

    user = platform_main.UserSchema(
        user_id="u1", tenant_id="t1", role=platform_main._normalize_role("farmer"), name_ar="م"
    )
    auth = _client(urls["services/auth"])
    try:
        token = platform_main.create_token(user)
        jti = pyjwt.decode(token, options={"verify_signature": False})["jti"]
        assert platform_main.get_current_user("Bearer " + token).user_id == "u1"
        auth.setex(f"{REVOKED_PREFIX}{jti}", 60, "1")
        with pytest.raises(HTTPException) as exc:
            platform_main.get_current_user("Bearer " + token)
        assert exc.value.status_code == 401

        from api.routers import auth as auth_router

        token2 = platform_main.create_token(user)
        jti2 = pyjwt.decode(token2, options={"verify_signature": False})["jti"]
        who = platform_main.get_current_user("Bearer " + token2)
        auth_router.auth_logout(authorization="Bearer " + token2, user=who)
        assert auth.exists(f"{REVOKED_PREFIX}{jti2}") == 1, "خروجُ المنصّة لم يبلغ خادمَ auth"
    finally:
        with contextlib.suppress(Exception):
            auth.close()
