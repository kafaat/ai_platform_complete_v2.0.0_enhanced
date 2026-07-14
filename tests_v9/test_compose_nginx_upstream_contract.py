"""حارس ساكن: كل upstream في بوّابة nginx يشير إلى خدمة compose حقيقيّة بمنفذها الصحيح.

خلفيّة (تدقيق البوّابة §1/§12 — acceptance test ``compose-nginx-port-contract``):
كل ``upstream … { server HOST:PORT; }`` في ``nginx/nginx.v9.conf`` يجب أن يكون HOST
خدمةً موجودة في ``docker-compose.v9.yml`` وPORT مطابقاً لمنفذها الداخليّ — كي لا يشير
عاكسٌ إلى خدمة/منفذ غير موجودين. حارس ثابت لا يتطلّب رفع الخدمات.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

# مضيفات بنية تحتيّة/بديلة معروفة قد تظهر في upstreams خارج compose الأساسيّ.
_KNOWN_EXTRA_HOSTS = {"sahool-frontend"}


def _compose_services() -> tuple[set[str], dict[str, int]]:
    doc = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")) or {}
    names: set[str] = set(_KNOWN_EXTRA_HOSTS)
    ports: dict[str, int] = {}
    for name, spec in (doc.get("services") or {}).items():
        names.add(name)
        if not isinstance(spec, dict) or name in ports:
            continue
        hc = str(spec.get("healthcheck", {}))
        m = re.search(r"(?:localhost|127\.0\.0\.1):(\d{2,5})", hc)
        if m:
            ports[name] = int(m.group(1))
            continue
        for p in spec.get("ports", []) or []:
            mm = re.match(r"^(?:[\d.]+:)?\d+:(\d+)", str(p))
            if mm:
                ports[name] = int(mm.group(1))
                break
    return names, ports


_UPSTREAM_RE = re.compile(r"upstream\s+\w+\s*\{\s*server\s+(sahool-[a-z0-9-]+):(\d+)")


def test_every_nginx_upstream_maps_to_a_real_compose_service_and_port() -> None:
    raw = (ROOT / "nginx/nginx.v9.conf").read_text(encoding="utf-8")
    # جرّد تعليقات nginx (# حتى نهاية السطر) كي لا تُفحَص upstreams مُعطَّلة بالتعليق.
    conf = "\n".join(re.sub(r"#.*$", "", line) for line in raw.splitlines())
    upstreams = _UPSTREAM_RE.findall(conf)
    assert upstreams, "no nginx upstreams parsed — check nginx.v9.conf format"

    names, ports = _compose_services()
    unknown: list[str] = []
    wrong_port: list[str] = []
    for host, port in upstreams:
        if host not in names:
            unknown.append(f"{host}:{port} (no compose service)")
            continue
        expected = ports.get(host)
        if expected is not None and int(port) != expected:
            wrong_port.append(f"{host}:{port} (compose port :{expected})")

    problems = unknown + wrong_port
    assert not problems, "nginx upstream ↔ compose drift:\n" + "\n".join(problems)
