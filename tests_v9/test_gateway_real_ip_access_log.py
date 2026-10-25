"""RATE-LIMIT-KEY-IS-A-RAILWAY-NODE-NOT-THE-CLIENT-01: the gateway logs X-Real-IP, and nothing else moves.

The Railway gateway is ``frontend/nginx.conf`` rendered by ``deploy/railway/render_frontend.py``
(``deploy/railway/Dockerfile.frontend``). Its rate-limit key is a Railway edge node, not the
client (``certification/evidence/edge_hop_measure_staging_20261018/README.md``). Choosing a
better key needs one measurement first: does Railway's edge overwrite a client-supplied
``X-Real-IP``? The access log could not show it, because it did not carry ``$http_x_real_ip``.

This file pins the measurement-only change:

* the gateway server logs with a format that carries ``$http_x_forwarded_for``,
  ``$http_x_real_ip`` and the limiter key, in the source and in the Railway-rendered config;
* every ``limit_req_zone``, the two key maps, the loopback exemption, and every
  ``proxy_set_header X-Real-IP`` / ``X-Forwarded-For`` are exactly what ``main@eb0be3977``
  carried, so logging cannot have changed which bucket a request lands in or what auth sees.

Each check also runs against a mutated copy, so a check that cannot see the defect fails here
instead of passing an empty scan. Runbook: ``docs/runbooks/RATE_LIMIT_REAL_IP_MEASUREMENT.md``.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
_RENDER = ROOT / "deploy/railway/render_frontend.py"
_ENV = {
    "SAHOOL_AUTH_UPSTREAM": "sahool-auth-main.railway.internal:8000",
    "SAHOOL_PLATFORM_UPSTREAM": "sahool-platform.railway.internal:8000",
}
LOG_FORMAT = "sahool_edge"
# The nginx image's default "main" format; the new format keeps it as a prefix so the
# 2026-10-18 raw evidence lines and the new lines parse the same way up to the XFF field.
MAIN_PREFIX = (
    '$remote_addr - $remote_user [$time_local] "$request" '
    '$status $body_bytes_sent "$http_referer" '
    '"$http_user_agent" "$http_x_forwarded_for"'
)
REQUIRED_LOG_VARIABLES = ("$http_x_forwarded_for", "$http_x_real_ip", "$sahool_rl_key")

# ── Snapshot of main@eb0be3977 (frontend/nginx.conf), taken with the parser below. ──
MAIN_ZONES = [
    ("$sahool_rl_key", "zone=sahool_api:10m", "rate=20r/s"),
    ("$sahool_rl_key", "zone=sahool_tiles:10m", "rate=50r/s"),
    ("$sahool_rl_key", "zone=sahool_auth:10m", "rate=5r/s"),
]
MAIN_KEY_MAPS = {
    ("$http_x_forwarded_for", "$sahool_client_addr"): [
        ("~(?:^|,)\\s*(?<sahool_xff_last>[^,\\s]+)\\s*$", ("$sahool_xff_last",)),
        ("default", ("$remote_addr",)),
    ],
    ("$sahool_rl_exempt", "$sahool_rl_key"): [
        ("1", ("",)),
        ("default", ("$sahool_client_addr",)),
    ],
}
MAIN_EXEMPT_GEO = [("default", ("0",)), ("127.0.0.1", ("1",)), ("::1", ("1",))]
_PROXIED = (
    "= /api/ai-agronomist/healthz",
    "^~ /api/raster/",
    "^~ /api/vegetation/",
    "^~ /api/remote-sensing-workspace/",
    "^~ /api/indicators/",
    "^~ /api/weather/",
    "= /api/agent/health",
    "^~ /api/agent/",
    "^~ /api/guardrails/",
    "^~ /api/segmentation/",
    "/api/",
    "/auth/",
    "= /runtime-identity",
)
MAIN_CLIENT_HEADERS = Counter(
    {
        **{(loc, "x-real-ip", "$remote_addr"): 1 for loc in _PROXIED},
        **{(loc, "x-forwarded-for", "$proxy_add_x_forwarded_for"): 1 for loc in _PROXIED},
    }
)


@dataclass
class Node:
    name: str
    args: list[str]
    children: list[Node] | None = None
    parent: Node | None = field(default=None, repr=False)

    def directives(self, name: str) -> list[Node]:
        return [c for c in self.children or [] if c.name == name]

    def walk(self):
        for child in self.children or []:
            yield child
            yield from child.walk()


def _tokens(text: str):
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch == "#":
            i = text.find("\n", i)
            i = n if i == -1 else i
        elif ch in "{};":
            yield ch
            i += 1
        elif ch in "\"'":
            j = i + 1
            while text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            yield text[i + 1 : j]
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "{};":
                j += 1
            yield text[i:j]
            i = j


def parse(text: str) -> Node:
    root = Node("http", [], [])
    stack, words = [root], []
    for tok in _tokens(text):
        if tok == ";":
            stack[-1].children.append(Node(words[0], words[1:], None, stack[-1]))
            words = []
        elif tok == "{":
            block = Node(words[0], words[1:], [], stack[-1])
            stack[-1].children.append(block)
            stack.append(block)
            words = []
        elif tok == "}":
            assert not words, f"directive without ';' before '}}': {words}"
            stack.pop()
        else:
            words.append(tok)
    assert len(stack) == 1 and not words, "unbalanced nginx braces"
    return root


def _gateway_server(root: Node) -> Node:
    servers = [
        s
        for s in root.directives("server")
        if not any(a.startswith("unix:") for d in s.directives("listen") for a in d.args)
    ]
    assert len(servers) == 1, "expected exactly one TCP gateway server"
    return servers[0]


def _render(source: str) -> str:
    spec = importlib.util.spec_from_file_location("railway_render_frontend_real_ip", _RENDER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.render(source, _ENV, ["10.0.0.2"])


def _entries(block: Node) -> list[tuple[str, tuple[str, ...]]]:
    return [(c.name, tuple(c.args)) for c in block.children or []]


def log_problems(text: str) -> list[str]:
    """What is wrong with the gateway's access log for this measurement ([] = fine)."""
    root = parse(text)
    server = _gateway_server(root)
    problems = []
    formats = {d.args[0]: "".join(d.args[1:]) for d in root.directives("log_format")}
    fmt = formats.get(LOG_FORMAT)
    if fmt is None:
        return [f"no http-level `log_format {LOG_FORMAT}`"]
    if not fmt.startswith(MAIN_PREFIX):
        problems.append(f"{LOG_FORMAT} does not start with the image's 'main' format")
    problems += [f"{LOG_FORMAT} lacks {v}" for v in REQUIRED_LOG_VARIABLES if v not in fmt]
    logs = [d.args for d in server.directives("access_log")]
    if not any(len(a) >= 2 and a[1] == LOG_FORMAT for a in logs):
        problems.append(f"gateway server does not log with {LOG_FORMAT}: {logs}")
    if root.directives("access_log"):
        problems.append("http-level access_log here would duplicate the image's 'main' log")
    for loc in server.directives("location"):
        for d in loc.directives("access_log"):
            if d.args != ["off"]:
                problems.append(f"location {' '.join(loc.args)} overrides the log: {d.args}")
    return problems


def key_problems(text: str) -> list[str]:
    """Differences from main in anything that decides the limiter key or upstream headers."""
    root = parse(text)
    problems = []
    zones = [tuple(z.args) for z in root.directives("limit_req_zone")]
    if zones != MAIN_ZONES:
        problems.append(f"limit_req_zone changed: {zones}")
    maps = {tuple(m.args): _entries(m) for m in root.directives("map")}
    for key, entries in MAIN_KEY_MAPS.items():
        if maps.get(key) != entries:
            problems.append(f"map {key} changed: {maps.get(key)}")
    geos = [_entries(g) for g in root.directives("geo")]
    if geos != [MAIN_EXEMPT_GEO]:
        problems.append(f"loopback exemption changed: {geos}")
    for name in ("real_ip_header", "set_real_ip_from", "real_ip_recursive"):
        if any(n.name == name for n in root.walk()):
            problems.append(f"`{name}` would rewrite $remote_addr and every header built on it")
    headers = Counter()
    for node in root.walk():
        if node.name != "proxy_set_header" or not node.args:
            continue
        header = node.args[0].lower()
        if header not in {"x-real-ip", "x-forwarded-for"}:
            continue
        where = " ".join(node.parent.args) if node.parent.name == "location" else node.parent.name
        headers[(where, header, " ".join(node.args[1:]))] += 1
    if headers != MAIN_CLIENT_HEADERS:
        added = sorted((headers - MAIN_CLIENT_HEADERS).elements())
        removed = sorted((MAIN_CLIENT_HEADERS - headers).elements())
        problems.append(f"client-address headers changed: added {added}, removed {removed}")
    return problems


CONFIGS = {"source": SOURCE, "railway_rendered": _render(SOURCE)}


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_gateway_access_log_carries_x_real_ip_and_x_forwarded_for(name):
    assert log_problems(CONFIGS[name]) == []


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_rate_limit_key_and_client_headers_are_unchanged_from_main(name):
    assert key_problems(CONFIGS[name]) == []


def test_the_log_check_rejects_mains_log_shape():
    """Falsification: main had no log_format/access_log in this file, so the check must fail."""
    lines = SOURCE.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith(f"log_format {LOG_FORMAT}"))
    end = next(i for i in range(start, len(lines)) if lines[i].rstrip().endswith(";"))
    without = "".join(lines[:start] + lines[end + 1 :])
    without = without.replace(f"    access_log /dev/stdout {LOG_FORMAT};\n", "")
    assert without != SOURCE
    assert log_problems(without) == [f"no http-level `log_format {LOG_FORMAT}`"]
    no_real_ip = SOURCE.replace('xrip="$http_x_real_ip" ', "")
    assert f"{LOG_FORMAT} lacks $http_x_real_ip" in log_problems(no_real_ip)
    no_access_log = SOURCE.replace(f"access_log /dev/stdout {LOG_FORMAT};", "")
    assert any("does not log with" in p for p in log_problems(no_access_log))


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            "proxy_set_header   X-Real-IP         $remote_addr;",
            "proxy_set_header   X-Real-IP         $http_x_real_ip;",
            "client-address headers changed",
        ),
        (
            "proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;",
            "proxy_set_header   X-Forwarded-For   $http_x_forwarded_for;",
            "client-address headers changed",
        ),
        (
            "limit_req_zone $sahool_rl_key zone=sahool_auth:10m",
            "limit_req_zone $http_x_real_ip zone=sahool_auth:10m",
            "limit_req_zone changed",
        ),
        ("    default $sahool_client_addr;", "    default $http_x_real_ip;", "map ("),
        ("    ::1       1;", "    ::1       1;\n    10.0.0.0/8 1;", "loopback exemption"),
        ("server_tokens off;", "server_tokens off;\n    real_ip_header X-Real-IP;", "real_ip"),
    ],
)
def test_the_key_check_sees_each_kind_of_change(old, new, expected):
    """Falsification: one changed key, map or header line must turn the check red."""
    assert old in SOURCE
    mutated = SOURCE.replace(old, new, 1)
    assert any(expected in p for p in key_problems(mutated)), key_problems(mutated)
