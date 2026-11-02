"""S10: the Railway gateway (frontend/nginx.conf) sends a strict Content-Security-Policy.

Before this contract the only CSP lived in nginx/nginx.v9.conf (with script
'unsafe-inline'); the gateway that actually serves the SPA on Railway sent none,
so any HTML-injection sink in the app ran attacker script.

بوّابة Railway ترسل CSP صارمة: لا 'unsafe-inline' للسكربت، والمضيفات الخارجيّة
مشتقّة من سجلّ الطبقات لا مكتوبة تخميناً.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
CONF = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
CSP_LINE = re.compile(r'^\s*add_header\s+Content-Security-Policy\s+"([^"]*)"\s+always;', re.M)


def _block(raw: str, declaration: str) -> str:
    assert raw.count(declaration) == 1, declaration
    start = raw.index(declaration) + len(declaration)
    depth = 1
    for index in range(start, len(raw)):
        if raw[index] == "{":
            depth += 1
        elif raw[index] == "}":
            depth -= 1
            if depth == 0:
                return raw[start:index]
    raise AssertionError("Unclosed configuration block")


def _server_level(raw: str) -> str:
    """The server block with every nested block removed (only server-level directives)."""
    body = _block(raw, "server {")
    out, depth = [], 0
    for ch in body:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def _directives(policy: str) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for part in policy.split(";"):
        tokens = part.split()
        if tokens:
            assert tokens[0] not in parsed, f"duplicate directive {tokens[0]}"
            parsed[tokens[0]] = tokens[1:]
    return parsed


def _document_policies() -> list[str]:
    server = CSP_LINE.findall(_server_level(CONF))
    shell = CSP_LINE.findall(_block(CONF, "location = /index.html {"))
    assert len(server) == 1, "server-level CSP missing: SPA routes/API answers would carry none"
    assert len(shell) == 1, (
        "location = /index.html has its own add_header, so it must repeat the CSP"
    )
    assert server == shell, "the SPA shell and the server level must send the same policy"
    return server


def test_gateway_sends_csp_on_the_spa_document():
    (policy,) = _document_policies()
    d = _directives(policy)
    assert d["default-src"] == ["'self'"]
    assert d["object-src"] == ["'none'"]
    assert d["base-uri"] == ["'self'"]
    assert d["form-action"] == ["'self'"]
    # Same stance as X-Frame-Options SAMEORIGIN on the same responses.
    assert d["frame-ancestors"] == ["'self'"]


def test_script_src_has_no_inline_eval_or_wildcard():
    (policy,) = _document_policies()
    d = _directives(policy)
    script = d["script-src"]
    for forbidden in ("'unsafe-inline'", "'unsafe-eval'", "*", "data:", "blob:", "https:", "http:"):
        assert forbidden not in script, f"script-src must not allow {forbidden}"
    assert set(script) <= {"'self'", "'wasm-unsafe-eval'"}, script
    # 'unsafe-inline' is tolerated only for styles (Leaflet/MapLibre/popup style= attributes).
    for name, sources in d.items():
        if name != "style-src":
            assert "'unsafe-inline'" not in sources, name
            assert "'unsafe-eval'" not in sources, name


def _host_allowed(host: str, sources: list[str]) -> bool:
    for src in sources:
        pattern = src.removeprefix("https://")
        if pattern == host or (pattern.startswith("*.") and host.endswith(pattern[1:])):
            return True
    return False


def test_every_registered_basemap_host_is_allowed_for_leaflet_and_maplibre():
    """Derived from the app, not guessed: a new basemap host must be added to the CSP too."""
    (policy,) = _document_policies()
    d = _directives(policy)
    registry = (ROOT / "frontend/src/lib/layerRegistry.ts").read_text(encoding="utf-8")
    hosts = {h.replace("{s}", "a") for h in re.findall(r"source:\s*'https://([^/']+)/", registry)}
    assert hosts, "no https basemap source found in layerRegistry.ts"
    for host in sorted(hosts):
        assert _host_allowed(host, d["img-src"]), f"{host}: Leaflet <img> tiles blocked"
        assert _host_allowed(host, d["connect-src"]), f"{host}: MapLibre fetch()ed tiles blocked"
    gl = (ROOT / "frontend/src/components/maphub/HubMapGL.tsx").read_text(encoding="utf-8")
    glyphs = re.search(r"glyphs:\s*'https://([^/']+)/", gl)
    assert glyphs and _host_allowed(glyphs.group(1), d["connect-src"])
    # MapLibre spawns its worker from a blob: URL.
    assert "blob:" in d["worker-src"]


def test_realtime_call_document_keeps_its_own_stricter_frame_policy():
    call = _block(CONF, "location = /realtime-call/ {")
    assert CSP_LINE.findall(call) == ["frame-ancestors 'none'"]
