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


_UPSTREAM_RE = re.compile(r"upstream\s+\w+\s*\{[^{}]*?\bserver\s+(sahool-[a-z0-9-]+):(\d+)")


@pytest.mark.parametrize("config", ["nginx/nginx.v9.conf", "frontend/nginx.conf"])
def test_every_nginx_upstream_maps_to_a_real_compose_service_and_port(config: str) -> None:
    raw = (ROOT / config).read_text(encoding="utf-8")
    # جرّد تعليقات nginx (# حتى نهاية السطر) كي لا تُفحَص upstreams مُعطَّلة بالتعليق.
    conf = "\n".join(re.sub(r"#.*$", "", line) for line in raw.splitlines())
    upstreams = _UPSTREAM_RE.findall(conf)
    assert upstreams, f"no nginx upstreams parsed — check {config} format"

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


def test_gateway_startup_is_not_blocked_by_backend_health() -> None:
    from tests_v9._nginx_contract import assert_dynamic_gateway_binding

    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    conf = (ROOT / "nginx/nginx.v9.conf").read_text(encoding="utf-8")
    uncommented = re.sub(r"#[^\n]*", "", conf)
    bindings = _UPSTREAM_RE.findall(uncommented)
    declared = re.findall(r"\bupstream\s+\w+\s*\{", uncommented)
    assert len(bindings) == len(declared) > 0, "a dynamic binding disappeared from the inventory"
    for host, _port in bindings:
        assert_dynamic_gateway_binding(conf, compose["services"], host)
    assert compose["services"]["sahool-nginx"]["image"] == "nginx:1.27.5-alpine"
    overlay = yaml.safe_load((ROOT / "docker-compose.v9.gpu.yml").read_text(encoding="utf-8"))
    assert "sahool-nginx" not in overlay["services"], "recheck the merged GPU gateway contract"


def test_frontend_healthcheck_and_non_root_image_contract() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    health = compose["services"]["sahool-frontend"]["healthcheck"]
    image = (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")
    options = re.search(r"^HEALTHCHECK (.+?) \\\n", image, re.M)
    assert options
    for flag, key in (
        ("interval", "interval"),
        ("timeout", "timeout"),
        ("start-period", "start_period"),
        ("retries", "retries"),
    ):
        assert f"--{flag}={health[key]}" in options[1].split()
    command = "wget --quiet --tries=1 --spider http://127.0.0.1:8080/healthz"
    assert health["test"] == ["CMD", *command.split()]
    assert f"CMD {command} || exit 1" in image
    assert "USER nginx" in image
    assert "rm -f /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh" in image
    assert "listen [::]:8080;" in (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")


@pytest.mark.parametrize("flags", ["", " resolve", " resolve weight=2 backup"])
def test_dns_inventory_sees_dynamic_and_plain_servers(flags: str) -> None:
    from scripts.ci.nginx_compose_dns_gate import upstream_hosts

    conf = f"upstream x {{ zone x 64k; server known:8080{flags}; }}"
    conf += "\n# upstream ignored { server stale:80; }\n"
    assert upstream_hosts(conf) == [("known", 8080)]


@pytest.mark.parametrize("body", ["server unknown:8080 resolve;", "# server known:8080;"])
def test_dns_gate_rejects_unknown_or_unmeasured_bindings(tmp_path, body: str) -> None:
    import subprocess
    import sys

    compose = tmp_path / "compose.yml"
    nginx = tmp_path / "nginx.conf"
    output = tmp_path / "result.json"
    compose.write_text("services:\n  known:\n    image: nginx:1.27.5-alpine\n", encoding="utf-8")
    nginx.write_text(f"upstream x {{ zone x 64k; {body}\n}}", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci/nginx_compose_dns_gate.py"),
            "--compose",
            str(compose),
            "--nginx",
            str(nginx),
            "--json",
            str(output),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAIL" in result.stdout
