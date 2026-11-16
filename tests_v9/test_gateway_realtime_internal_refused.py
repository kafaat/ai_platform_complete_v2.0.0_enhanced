"""W3-11: the gateway refuses realtime-session's worker-only ``internal/`` prefix.

``/api/v1/realtime/internal/*`` hands out the session bearer to the media worker. The gateway
must answer it at the edge and never proxy it, while ``/api/v1/realtime/*`` reaches
realtime-session. These checks resolve which ``location`` nginx would pick for a URI in the
TLS server, by nginx's own rule for prefix locations: the longest matching prefix wins, and
``^~`` stops the regex scan. A regex location could otherwise still take the request.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CONF = re.sub(r"#[^\n]*", "", (ROOT / "nginx/nginx.v9.conf").read_text(encoding="utf-8"))


def _tls_server() -> str:
    start = CONF.index("listen 443 ssl")
    depth, i = 0, CONF.rindex("server {", 0, start) + len("server ")
    for j in range(i, len(CONF)):
        depth += {"{": 1, "}": -1}.get(CONF[j], 0)
        if depth == 0:
            return CONF[i : j + 1]
    raise AssertionError("unterminated TLS server block")


def _locations(server: str) -> list[tuple[str, str, str]]:
    """``(modifier, path, body)`` for each top-level location in the server block."""
    out = []
    for m in re.finditer(r"location\s+(\^~|=|~\*|~)?\s*(\S+)\s*\{", server):
        depth, k = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(server[k], 0)
            k += 1
        out.append((m.group(1) or "", m.group(2), server[m.end() : k - 1]))
    return out


def _resolve(uri: str) -> tuple[str, str, str]:
    locs = _locations(_tls_server())
    exact = [loc for loc in locs if loc[0] == "=" and loc[1] == uri]
    if exact:
        return exact[0]
    prefixes = [loc for loc in locs if loc[0] in ("", "^~") and uri.startswith(loc[1])]
    best = max(prefixes, key=lambda loc: len(loc[1]))
    if best[0] == "^~":
        return best
    for loc in locs:
        if loc[0] in ("~", "~*"):
            flags = re.IGNORECASE if loc[0] == "~*" else 0
            if re.search(loc[1], uri, flags):
                return loc
    return best


@pytest.mark.parametrize(
    "uri",
    [
        "/api/v1/realtime/internal/",
        "/api/v1/realtime/internal/sessions/abc/worker-token",
        "/api/v1/realtime/internal/anything?x=1",
    ],
)
def test_the_internal_prefix_is_answered_at_the_edge_and_never_proxied(uri):
    modifier, path, body = _resolve(uri.split("?")[0])
    assert (modifier, path) == ("^~", "/api/v1/realtime/internal/"), (uri, modifier, path)
    assert re.search(r"\breturn\s+404\b", body), body
    assert "proxy_pass" not in body
    assert "realtime_backend" not in body


@pytest.mark.parametrize("uri", ["/api/v1/realtime/sessions", "/api/v1/realtime/sessions/abc/end"])
def test_the_public_prefix_reaches_realtime_session(uri):
    modifier, path, body = _resolve(uri)
    assert (modifier, path) == ("^~", "/api/v1/realtime/"), (uri, modifier, path)
    assert re.search(r"proxy_pass\s+http://realtime_backend;", body)
    assert 'proxy_set_header Cookie "";' in body


def test_a_near_miss_is_not_caught_by_the_internal_block():
    """``/api/v1/realtime/internalx`` is a public path; only the exact ``internal/`` prefix is refused."""
    _, path, _ = _resolve("/api/v1/realtime/internalx")
    assert path == "/api/v1/realtime/"
