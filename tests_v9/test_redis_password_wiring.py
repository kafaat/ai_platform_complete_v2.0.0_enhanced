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

import re
import shlex
from pathlib import Path

import pytest
import yaml
from redis.connection import parse_url

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

#: كلمةُ سرٍّ ستّ‑عشريّة (شكلُ ``openssl rand -hex``) تُستوفى مكانَ ``${REDIS_PASSWORD…}``.
#: تُبنى ولا تُكتَب حرفيّاً: سلسلةٌ ثابتة الشكل في الشيفرة تُقرأ سرّاً (gitleaks generic-api-key).
_PASSWORD = bytes(range(0x10, 0x20)).hex()
_INTERP = re.compile(r"\$\{REDIS_PASSWORD(?:[:?-][^}]*)?\}")

#: الحزمُ التي تُقلِع Redis بكلمة سرٍّ ولها عملاء — لكلٍّ منها عميلٌ واحدٌ على الأقلّ،
#: وإلّا صارت الخاصّيّةُ فارغةً فتمرّ بلا معنى.
_BUNDLES_WITH_CLIENTS = (
    "docker-compose.v9.yml",
    "docker-compose.fixed.yml",
    "docker-compose.light.yml",
    "docker-compose.unified.yml",
)


def _load(path: Path) -> dict:
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
