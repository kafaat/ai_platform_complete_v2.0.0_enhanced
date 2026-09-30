"""كلمةُ سرّ Redis: الخادمُ والعميلُ يجب أن يتّفقا عليها — مقيسةً بمحلِّل العميل نفسه.

``test_compose_redis_health.py`` يحرس **الخادم** (``--requirepass`` موجود، وفحصُ الصحّة
يُصادِق)، ولا شيءَ كان يحرس **العميل**. فأمكن أن يبقى الخادمُ أخضرَ وكلُّ عميلٍ ساقطاً.

العطلُ المقيس (2026-09-30، redis-server 7.0.15 + redis-py 5.3.1، بعد أن أبلغ تدقيقٌ حيّ
2026-09-29 عن «انجراف REDIS_PASSWORD»): ``docker-compose.light.yml`` و
``docker-compose.unified.yml`` يُقلِعان Redis بـ``--requirepass "${REDIS_PASSWORD}"``،
وروابطُ عملائهما (مرساةُ ``x-db-env`` وثلاثةٌ حرفيّة في كلٍّ) ``redis://<host>:6379/N`` بلا
كلمة سرّ — فكلُّ عميلٍ (6 في light و9 في unified بـ``docker compose config``) يُردّ
بـ``AuthenticationError: Authentication required`` ولو كانت ``.env`` سليمة.

الخاصّيّةُ تُقاس على الملفّات كما تُحلَّل (مراسي YAML مُستوفاة)، وكلمةُ السرّ تُستخرَج من
سطر أمر الخادم لا من افتراضٍ عنه، ورابطُ العميل يُفكّ بـ``redis.connection.parse_url`` —
المحلِّلُ الذي يستعمله كلُّ عميلٍ فعلاً — لا بتعبيرٍ نمطيّ يُعيد صياغة الشرط.
"""

from __future__ import annotations

import functools
import re
import shlex
from pathlib import Path

import pytest
import yaml
from redis.connection import parse_url

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

#: كلمةُ سرٍّ ستّ‑عشريّة (شكلُ ``openssl rand -hex``) تُستوفى مكانَ ``${REDIS_PASSWORD…}``.
_PASSWORD = "5f0c9e1ab3d24c7e8f6a1b2c3d4e5f60"
_INTERP = re.compile(r"\$\{REDIS_PASSWORD(?:[:?-][^}]*)?\}")

#: الحزمُ التي تُقلِع Redis بكلمة سرٍّ ولها عملاء — لكلٍّ منها عميلٌ واحدٌ على الأقلّ،
#: وإلّا صارت الخاصّيّةُ فارغةً فتمرّ بلا معنى.
_BUNDLES_WITH_CLIENTS = (
    "docker-compose.v9.yml",
    "docker-compose.fixed.yml",
    "docker-compose.light.yml",
    "docker-compose.unified.yml",
)


@functools.cache
def _load(path: Path) -> dict:
    """قراءةٌ فقط — مُخزَّنة لأنّ كلَّ حالةٍ مُعامَلة تقرأ ملفَّها."""
    return yaml.safe_load(_INTERP.sub(_PASSWORD, path.read_text(encoding="utf-8"))) or {}


def _env_items(svc: dict):
    env = svc.get("environment") or {}
    if isinstance(env, dict):
        yield from ((str(k), v) for k, v in env.items())
    else:
        for item in env:
            key, _, value = str(item).partition("=")
            yield key, value


def _requirepass(svc: dict) -> str | None:
    cmd = svc.get("command")
    argv = list(cmd) if isinstance(cmd, list) else shlex.split(str(cmd or ""))
    if "--requirepass" in argv:
        i = argv.index("--requirepass")
        return argv[i + 1] if i + 1 < len(argv) else ""
    return None


def _servers(doc: dict) -> dict[str, tuple[str, str]]:
    """اسمُ الشبكة (المفتاح/container_name/hostname) ⇒ (اسمُ الخدمة، كلمةُ السرّ المطلوبة)."""
    out: dict[str, tuple[str, str]] = {}
    for name, svc in (doc.get("services") or {}).items():
        if not isinstance(svc, dict) or "redis" not in str(svc.get("image", "")).lower():
            continue
        password = _requirepass(svc)
        if password is None:
            continue
        for alias in (name, svc.get("container_name"), svc.get("hostname")):
            if alias:
                out[str(alias)] = (name, password)
    return out


def _clients() -> list[tuple[str, str, str, dict, tuple[str, str]]]:
    rows = []
    for path in sorted(ROOT.glob("docker-compose*.yml")):
        doc = _load(path)
        servers = _servers(doc)
        if not servers:
            continue
        for name, svc in (doc.get("services") or {}).items():
            if not isinstance(svc, dict):
                continue
            for key, value in _env_items(svc):
                if not isinstance(value, str) or not value.startswith(("redis://", "rediss://")):
                    continue
                parsed = parse_url(value)
                if parsed.get("host") in servers:
                    rows.append((path.name, name, key, parsed, servers[parsed["host"]]))
    return rows


_CLIENTS = _clients()


def test_every_passworded_bundle_has_clients_to_check():
    """أرضيّةُ صدق: الخاصّيّةُ أدناه على مجموعةٍ فارغة تمرّ بلا معنى."""
    seen = {row[0] for row in _CLIENTS}
    missing = [b for b in _BUNDLES_WITH_CLIENTS if b not in seen]
    assert not missing, f"لم يُعثَر على عميل Redis في: {missing} — انهار التحليل"
    assert len(_CLIENTS) >= 30, len(_CLIENTS)


@pytest.mark.parametrize(
    "fname,service,key,parsed,server",
    _CLIENTS,
    ids=[f"{r[0]}::{r[1]}::{r[2]}" for r in _CLIENTS],
)
def test_client_url_carries_the_password_its_server_requires(fname, service, key, parsed, server):
    server_name, required = server
    assert parsed.get("password") == required, (
        f"{fname}: {service}.{key} يتّصل بـ{server_name} (requirepass مضبوط) "
        f"بكلمة سرّ {parsed.get('password')!r} ⇒ `Authentication required` عند كلّ اتّصال. "
        "اكتب الرابط `redis://:${REDIS_PASSWORD:?…}@<host>:6379/N` كما في docker-compose.v9.yml."
    )


def _depends_on(path_name: str, service: str) -> dict:
    svc = _load(ROOT / path_name)["services"][service]
    deps = svc.get("depends_on") or {}
    return {d: {} for d in deps} if isinstance(deps, list) else dict(deps)


@pytest.mark.parametrize(
    "fname,service,key,parsed,server",
    _CLIENTS,
    ids=[f"{r[0]}::{r[1]}::{r[2]}" for r in _CLIENTS],
)
def test_a_client_that_waits_for_redis_waits_for_the_one_it_talks_to(
    fname, service, key, parsed, server
):
    """من ينتظر Redis ينتظر الذي يتّصل به — لا جارَه.

    العطلُ المقيس في ``docker-compose.v9.yml``: ``sahool-auth`` و``sahool-guardrails-engine``
    يتّصلان بـ``sahool-redis-state`` ويعتمدان (``service_healthy``) على ``sahool-redis``،
    ولا خدمةَ واحدة تعتمد على ``sahool-redis-state``: فلا ``up sahool-nginx`` (39 خدمة في
    إغلاق depends_on) ولا ``up sahool-auth`` يُقلِعه، ولا ترتيبَ يسبقه. و auth يلتقط Redis
    **مرّةً عند الإقلاع**: في التطوير (``SAHOOL_ENV`` الافتراضيّ في v9 و``.env.example``)
    يتنازل إلى ``_redis = None`` طوالَ عمر العمليّة — إبطالُ التوكنات وقفلُ الحساب معطَّلان
    بصمت (``services/auth/main.py``)؛ وفي الإنتاج يرفض الإقلاع.
    """
    doc = _load(ROOT / fname)
    redis_services = {name for name, _ in _servers(doc).values()}
    deps = _depends_on(fname, service)
    waits_for = sorted(d for d in deps if d in redis_services)
    target, _ = server
    if not waits_for:
        return  # لا ينتظر أيَّ Redis — صنفٌ آخر خارج هذه الخاصّيّة
    assert target in waits_for, (
        f"{fname}: {service}.{key} يتّصل بـ{target} وينتظر {waits_for} — "
        f"أضف `{target}: {{condition: service_healthy}}` إلى depends_on."
    )
    assert deps[target].get("condition", "service_healthy") == "service_healthy", deps[target]


# ── شكلُ كلمة السرّ: الرابطُ يحملها حرفيّاً بلا ترميز ────────────────────────────


def _env_example_guidance(name: str) -> str:
    """التعليقُ المتّصل فوق ``NAME=`` في ``.env.example``."""
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    idx = next(i for i, line in enumerate(lines) if line.startswith(f"{name}="))
    block = []
    for line in reversed(lines[:idx]):
        if not line.startswith("#"):
            break
        block.append(line)
    return "\n".join(reversed(block))


def test_env_example_tells_the_operator_to_generate_a_url_safe_redis_password():
    """``.env.example`` يسمّي مولِّداً ستّ‑عشريّاً لـ``REDIS_PASSWORD``.

    العطلُ المقيس: كان التعليقُ «نفس كلمة السرّ تُستخدَم في requirepass وفي REDIS_URL»
    — و``REDIS_URL`` في الملفّ نفسه ``localhost`` بلا كلمة سرّ — ولا مولِّدَ ولا قيدَ شكل،
    بينما ``JWT_SECRET`` في رأس الملفّ يقول ``openssl rand -hex 32``. فالمُشغِّل يولِّد بما
    اعتاد، و``openssl rand -base64 32`` يُنتِج ``/`` في قرابة نصف السحبات.
    """
    guidance = _env_example_guidance("REDIS_PASSWORD")
    assert re.search(r"openssl rand -hex \d+", guidance), guidance


def test_a_hex_password_round_trips_through_every_client_url_and_base64_does_not():
    """لماذا الإرشادُ حاملٌ لا زينة: الشكلُ الستّ‑عشريّ يعبر الرابطَ حرفيّاً والآخرُ لا.

    يُستوفى كلُّ رابط عميلٍ فعليّ بكلمتَي سرّ ويُفكّ بمحلِّل العميل. الستّ‑عشريّةُ تعود
    كما هي في كلّ رابط؛ وسحبةُ base64 فيها ``/`` لا تعود في أيّ رابط.
    """
    raw_urls = []
    for path in sorted(ROOT.glob("docker-compose*.yml")):
        raw_urls += re.findall(r"redis://:\$\{REDIS_PASSWORD[^}]*\}@[^\s\"']+", path.read_text())
    assert len(raw_urls) >= 25, len(raw_urls)  # 29 موضعاً نصّيّاً مقيساً (المرساةُ مرّةً)
    hex_pw, b64_pw = "9c2e" * 16, "q0Zk/8Xr+Jm2Lw4="
    for url in raw_urls:
        assert parse_url(_INTERP.sub(hex_pw, url)).get("password") == hex_pw, url
        try:
            decoded = parse_url(_INTERP.sub(b64_pw, url)).get("password")
        except ValueError:
            decoded = None  # `Port could not be cast to integer` — العطلُ المقيس نفسه
        assert decoded != b64_pw, url
