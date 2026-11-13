"""MOBILE-BACKEND-CONTRACT-01: every HTTP call in the Flutter app reaches a real handler.

**What this replaces.** The previous version of this file kept a hand-written
``MOBILE_CALLS`` list for a React Native app (``sahool_mobile/src/api/*.ts``) that is not in
this repository, and its two tests *returned* a list of ``("✓"|"✗", msg)`` tuples instead of
asserting. pytest ignores a test's return value, so both tests passed while reporting all
19 of their own calls as missing (the backend scan read ``api/main.py``, which holds no
routes since the router decomposition). It could not fail.

**What this guard proves.** The real mobile app is Flutter, under ``mobile/sahool_app/lib``.
Its calls go through ``ApiClient`` (``core/network/api_client.dart``), whose Dio base URL is
the bare gateway origin (``AppConfig.apiUri``), so every request path is a public gateway
path written in Dart. This file:

1. lexes every Dart file (comments excluded, nested ``${...}`` interpolation understood) and
   takes every string literal that is a public gateway path (``/api/...`` or ``/auth/...``),
   after resolving a leading same-file constant, getter or one-line function
   (``'$_base/entries'``, ``'${_f(fieldId)}/seasons'``, ``'$rasterPrefix/v1/...'``). The HTTP
   method is attributed when the literal (or a constant naming it) is the path argument of
   ``.get/.post/.put/.patch/.delete``, of ``.send('METHOD', ...)``, or of an outbox
   operation's ``method: 'X', path: ...``;
2. routes the public path through ``nginx/nginx.v9.conf`` the way nginx does (exact
   location, then longest prefix unless a regex location matches first, then
   ``rewrite ... break`` and the ``proxy_pass`` URI replacement, plus the gateway ``map``
   rewrites), giving the upstream and the path the service receives;
3. maps the upstream host to its service through ``docker-compose.v9.yml`` (the host is
   the compose service, whose Dockerfile lives in ``services/<service>/``);
4. requires a route with that method and path **in that service** in the committed,
   CI-drift-checked ``route_inventory.generated.json``. Path matching reuses the web guard
   (``tests_v9/test_frontend_api_v1_literal_has_server_route.py``): a literal segment
   never satisfies a route parameter, and the method is part of the match.

**Auth contract (verified, not assumed).** The old test claimed mobile auth paths must
carry ``/api/v1``. That is false for this client: ``AuthApi`` and the refresh in
``ApiClient`` call ``/auth/login``, ``/auth/refresh``, ``/auth/logout``..., which the
gateway's ``location /auth/`` rewrites to the auth service's ``/v1/auth/*``. The platform
only mirrors four of them under ``/api/v1/auth`` (no refresh, no MFA), so the contract
asserted here is that every mobile auth call reaches the **auth service**.

**What it does not prove (declared, not hidden).** A path assembled at runtime from
variables the scan cannot resolve is invisible; a constant from another file is resolved
only when its name is unique across ``lib/``. A literal whose method cannot be attributed
is matched against any method. A platform catch-all proxy route
(``ANY /api/edge/{path:path}``, ``ANY /api/field-forms/{path:path}``) is matched at the
platform hop; the hop behind it is not followed here. The notification WebSocket
(``$wsUri/ws/notifications``) is not an HTTP call and is out of scope.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
DART_LIB = ROOT / "mobile/sahool_app/lib"
ROUTE_INVENTORY = ROOT / "route_inventory.generated.json"
GATEWAY_CONF = ROOT / "nginx/nginx.v9.conf"
COMPOSE = ROOT / "docker-compose.v9.yml"

#: Public gateway prefixes a mobile request path starts with (base URL = bare origin).
PUBLIC_PREFIXES = ("/api/", "/auth/")

_WEB_GUARD_SPEC = importlib.util.spec_from_file_location(
    "_mobile_contract_web_route_guard",
    ROOT / "tests_v9/test_frontend_api_v1_literal_has_server_route.py",
)
web_guard = importlib.util.module_from_spec(_WEB_GUARD_SPEC)
assert _WEB_GUARD_SPEC.loader is not None
sys.modules[_WEB_GUARD_SPEC.name] = web_guard
_WEB_GUARD_SPEC.loader.exec_module(web_guard)

#: Mobile calls with no backend handler today. Each is a real finding, listed so the
#: guard passes on main without hiding it. Key: (dart file, method or "ANY", public path
#: with parameters normalised to ``{}``). A new entry is not a fix; an entry that starts
#: matching (or whose call disappears) must be deleted (see the staleness test).
_REALTIME_GATEWAY_GAP = (
    "services/realtime-session serves this route, but the public gateway nginx/nginx.v9.conf "
    "has no realtime location: `location /api/v1/` sends it to sahool-platform, which has no "
    "/api/v1/realtime/* handler, so a mobile build pointed at the gateway gets 404. Only the "
    "web origin's frontend/nginx.conf routes it (`location ^~ /api/v1/realtime/` to "
    "sahool-realtime-session, with `/api/v1/realtime/internal/` refused)."
)
_REALTIME_OWNER = (
    "owner decision (gateway + realtime-session): add the same `^~ /api/v1/realtime/` "
    "location (and the internal/ refusal) to nginx.v9.conf, or document that the mobile "
    "API_URL must be the web origin. Found by MOBILE-BACKEND-CONTRACT-01, 2026-11-13."
)
KNOWN_MOBILE_CALLS_WITHOUT_BACKEND: dict[tuple[str, str, str], dict[str, str]] = {
    (
        "mobile/sahool_app/lib/features/realtime/realtime_api.dart",
        "POST",
        "/api/v1/realtime/sessions",
    ): {"reason": _REALTIME_GATEWAY_GAP, "owner": _REALTIME_OWNER},
    (
        "mobile/sahool_app/lib/features/realtime/realtime_api.dart",
        "DELETE",
        "/api/v1/realtime/sessions/{}",
    ): {"reason": _REALTIME_GATEWAY_GAP, "owner": _REALTIME_OWNER},
}


# ── Dart lexing ─────────────────────────────────────────────────────────────


class DartLexError(ValueError):
    pass


@dataclass(frozen=True)
class DartLiteral:
    start: int  # index of the opening quote (or of the ``r`` prefix)
    end: int  # index just past the closing quote
    body: str  # text between the quotes, interpolations kept verbatim
    raw: bool


def _skip_string(text: str, i: int) -> tuple[int, str, bool]:
    """``text[i]`` opens a string (optionally ``r``-prefixed); return (end, body, raw)."""
    raw = text[i] in "rR"
    if raw:
        i += 1
    quote = text[i : i + 3] if text[i : i + 3] in ("'''", '"""') else text[i]
    body_start = i + len(quote)
    j = body_start
    n = len(text)
    while j < n:
        if text.startswith(quote, j):
            return j + len(quote), text[body_start:j], raw
        c = text[j]
        if len(quote) == 1 and c == "\n":
            break
        if not raw and c == "\\":
            j += 2
            continue
        if not raw and text.startswith("${", j):
            j = _skip_code(text, j + 2, closer="}")
            continue
        j += 1
    raise DartLexError(f"unterminated string at offset {i}")


def _skip_comment(text: str, i: int) -> int:
    if text.startswith("//", i):
        j = text.find("\n", i)
        return len(text) if j == -1 else j
    depth, j = 0, i
    while j < len(text):  # Dart block comments nest
        if text.startswith("/*", j):
            depth, j = depth + 1, j + 2
        elif text.startswith("*/", j):
            depth, j = depth - 1, j + 2
            if depth == 0:
                return j
        else:
            j += 1
    raise DartLexError(f"unterminated comment at offset {i}")


def _starts_string(text: str, i: int) -> bool:
    c = text[i]
    if c in "'\"":
        return True
    prev = text[i - 1] if i else ""
    return (
        c in "rR"
        and i + 1 < len(text)
        and text[i + 1] in "'\""
        and not (prev.isalnum() or prev in "_$")
    )


def _skip_code(text: str, i: int, closer: str) -> int:
    """Skip code up to the matching ``closer`` (inside ``${...}``); return index past it."""
    depth = 0
    while i < len(text):
        if text.startswith(("//", "/*"), i):
            i = _skip_comment(text, i)
        elif _starts_string(text, i):
            i = _skip_string(text, i)[0]
        elif text[i] == "{":
            depth, i = depth + 1, i + 1
        elif text[i] == "}":
            if depth == 0:
                return i + 1
            depth, i = depth - 1, i + 1
        else:
            i += 1
    raise DartLexError(f"unterminated interpolation before offset {i}")


def lex_dart(text: str) -> tuple[list[DartLiteral], str]:
    """Top-level string literals, and the text with comments blanked (newlines kept)."""
    literals: list[DartLiteral] = []
    masked = list(text)
    i = 0
    while i < len(text):
        if text.startswith(("//", "/*"), i):
            j = _skip_comment(text, i)
            for k in range(i, j):
                if masked[k] != "\n":
                    masked[k] = " "
            i = j
        elif _starts_string(text, i):
            end, body, raw = _skip_string(text, i)
            literals.append(DartLiteral(i, end, body, raw))
            i = end
        else:
            i += 1
    return literals, "".join(masked)


# ── call extraction ─────────────────────────────────────────────────────────

_IDENT = r"[A-Za-z_]\w*"
_HTTP_VERB = r"(get|post|put|patch|delete|head)"
_GENERIC = r"(?:<[^()]*>)?"
# A literal (or a constant) directly in the path argument position.
_METHOD_BEFORE = (
    re.compile(r"\.\s*" + _HTTP_VERB + r"\s*" + _GENERIC + r"\s*\(\s*$"),
    re.compile(r"\.\s*send\s*\(\s*['\"](\w+)['\"]\s*,\s*$"),
    re.compile(r"\bmethod\s*:\s*['\"](\w+)['\"]\s*,\s*path\s*:\s*$"),
)
# A definition whose value is the literal that follows.
_DEFINITION_BEFORE = (
    re.compile(r"\b(?:const|final)\s+(?:String\??\s+)?(" + _IDENT + r")\s*=\s*$"),
    re.compile(r"\bString\??\s+get\s+(" + _IDENT + r")\s*=>\s*$"),
    re.compile(r"\bString\??\s+(" + _IDENT + r")\s*\([^()]*\)\s*=>\s*$"),
    re.compile(r"\bString\??\s+get\s+(" + _IDENT + r")\s*\{[^{}]*\breturn\s+$"),
)
# A named constant/function used as the path argument.
_NAME_ARG = r"(?:" + _IDENT + r"\.)?(" + _IDENT + r")\s*(?:\([^()]*\))?\s*[,)]"
_METHOD_WITH_NAME = (
    re.compile(r"\.\s*" + _HTTP_VERB + r"\s*" + _GENERIC + r"\s*\(\s*" + _NAME_ARG),
    re.compile(r"\.\s*send\s*\(\s*['\"](\w+)['\"]\s*,\s*" + _NAME_ARG),
    re.compile(r"\bmethod\s*:\s*['\"](\w+)['\"]\s*,\s*path\s*:\s*" + _NAME_ARG),
)
_LEADING_INTERPOLATION = re.compile(
    r"^\$(?:(?P<bare>" + _IDENT + r")|\{(?P<name>" + _IDENT + r")(?:\([^{}]*\))?\}|\{[^{}]*\})"
)
_INTERPOLATION = re.compile(r"\$\{(?:[^{}]|\{[^{}]*\})*\}|\$" + _IDENT)
_LOOKBACK = 240


@dataclass(frozen=True)
class MobileCall:
    file: str
    line: int
    path: str  # public path; parameters normalised to ``{}``, query dropped
    method: str | None
    prefix_only: bool

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.file, self.method or "ANY", self.path)


def _normalise(resolved: str) -> str:
    path = _INTERPOLATION.sub("{}", resolved).split("?", 1)[0]
    return re.sub(r"\{[^{}/]*\}", "{}", path)


def _joined(text: str, masked: str, literals: list[DartLiteral], index: int) -> tuple[str, int]:
    """Body of literal ``index`` plus adjacent (``'a' 'b'``) or ``+``-joined literals."""
    body, last = literals[index].body, index
    while last + 1 < len(literals):
        gap = masked[literals[last].end : literals[last + 1].start]
        if gap.strip() not in ("", "+"):
            break
        last += 1
        body += literals[last].body
    return body, last


def _definitions(text: str, masked: str, literals: list[DartLiteral]) -> dict[str, str]:
    found: dict[str, str] = {}
    i = 0
    while i < len(literals):
        before = masked[max(0, literals[i].start - _LOOKBACK) : literals[i].start]
        body, last = _joined(text, masked, literals, i)
        for pattern in _DEFINITION_BEFORE:
            match = pattern.search(before)
            if match and not literals[i].raw:
                found.setdefault(match.group(1), body)
                break
        i = last + 1
    return found


def _resolve(body: str, defs: dict[str, str], used: set[str], depth: int = 0) -> str:
    """Substitute a leading constant; drop a leading origin that precedes a public path."""
    match = _LEADING_INTERPOLATION.match(body)
    if not match or depth > 6:
        return body
    name = match.group("bare") or match.group("name")
    rest = body[match.end() :]
    if name and name in defs:
        used.add(name)
        return _resolve(defs[name] + rest, defs, used, depth + 1)
    tail = _resolve(rest, defs, used, depth + 1)
    # e.g. '$base$rasterPrefix' where base = dio.options.baseUrl (the gateway origin).
    return tail if tail.startswith(PUBLIC_PREFIXES) else body


def _method(masked: str, start: int) -> str | None:
    before = masked[max(0, start - _LOOKBACK) : start]
    for pattern in _METHOD_BEFORE:
        match = pattern.search(before)
        if match:
            return match.group(1).upper()
    return None


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan_dart(
    text: str, *, rel: str, global_defs: dict[str, str] | None = None
) -> list[MobileCall]:
    """Every public gateway path in executable Dart code, with its method when known."""
    literals, masked = lex_dart(text)
    defs = _definitions(text, masked, literals)
    used: set[str] = set()
    calls: list[MobileCall] = []
    pending: list[tuple[int, str, str | None]] = []
    i = 0
    while i < len(literals):
        body, last = _joined(text, masked, literals, i)
        if not literals[i].raw:
            resolved = _resolve(body, defs, used)
            if resolved.startswith(PUBLIC_PREFIXES):
                pending.append((literals[i].start, resolved, _method(masked, literals[i].start)))
        i = last + 1
    # Constants passed by name: `_client.post(observationsPath, ...)`, `send('POST', _p(id))`.
    lookup = {**(global_defs or {}), **defs}
    for pattern in _METHOD_WITH_NAME:
        for match in pattern.finditer(masked):
            name = match.group(2)
            if name not in lookup:
                continue
            resolved = _resolve(lookup[name], lookup, set())
            if resolved.startswith(PUBLIC_PREFIXES):
                pending.append((match.start(2), resolved, match.group(1).upper()))
    prefix_values = {_resolve(defs[name], defs, set()) for name in used}
    for offset, resolved, method in pending:
        path = _normalise(resolved)
        prefix_only = (resolved in prefix_values and method is None) or path.endswith("/")
        calls.append(MobileCall(rel, _line(text, offset), path, method, prefix_only))
    return calls


def _dart_files() -> list[Path]:
    return sorted(DART_LIB.rglob("*.dart"))


def _global_definitions(sources: dict[str, str]) -> dict[str, str]:
    """Constants unique across ``lib/`` (for ``TasksApi.taskPath(id)`` from another file)."""
    seen: dict[str, list[str]] = {}
    for text in sources.values():
        literals, masked = lex_dart(text)
        for name, value in _definitions(text, masked, literals).items():
            seen.setdefault(name, []).append(value)
    return {name: values[0] for name, values in seen.items() if len(set(values)) == 1}


@lru_cache(maxsize=1)
def mobile_calls() -> tuple[tuple[MobileCall, ...], tuple[tuple[str, str], ...]]:
    sources: dict[str, str] = {}
    unreadable: list[tuple[str, str]] = []
    for path in _dart_files():
        sources[path.relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8")
    readable: dict[str, str] = {}
    for rel, text in sources.items():
        try:
            lex_dart(text)
        except DartLexError as exc:
            unreadable.append((rel, str(exc)))
        else:
            readable[rel] = text
    global_defs = _global_definitions(readable)
    found: list[MobileCall] = []
    for rel, text in readable.items():
        found.extend(scan_dart(text, rel=rel, global_defs=global_defs))
    unique = sorted(set(found), key=lambda c: (c.file, c.line, c.path, c.method or ""))
    return tuple(unique), tuple(unreadable)


# ── gateway: public path → (upstream, service path) ─────────────────────────


@dataclass(frozen=True)
class Location:
    modifier: str  # "", "=", "^~", "~", "~*"
    pattern: str
    proxy_pass: str | None
    rewrites: tuple[tuple[str, str, str], ...]  # (regex, replacement, flag)
    line: int


def _strip_comment(line: str) -> str:
    out, quote = [], ""
    for c in line:
        if quote:
            quote = "" if c == quote else quote
        elif c in "'\"":
            quote = c
        elif c == "#":
            break
        out.append(c)
    return "".join(out)


def _blocks(conf: str):
    """Yield (header, body_lines, first_line) for every top-level-of-server ``location``."""
    lines = conf.splitlines()
    depth = 0
    server_depth = None
    current: tuple[str, list[str], int] | None = None
    for number, raw in enumerate(lines, start=1):
        line = _strip_comment(raw)
        stripped = line.strip()
        if server_depth is None and re.match(r"^server\s*\{", stripped):
            server_depth = depth + 1
            is_tls = False
        if (
            server_depth is not None
            and depth == server_depth
            and re.match(r"listen\s+443\b", stripped)
        ):
            is_tls = True
        opened_location = (
            server_depth is not None and depth == server_depth and stripped.startswith("location")
        )
        if opened_location:
            current = (stripped, [], number)
        elif current is not None:
            current[1].append(stripped)
        for c in line:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if current is not None and depth == server_depth:
                    yield (current, is_tls)
                    current = None
                if server_depth is not None and depth < server_depth:
                    server_depth = None


_LOCATION_HEAD = re.compile(r"^location\s+(?:(=|\^~|~\*|~)\s+)?(\S+)\s*\{(.*)$")


@lru_cache(maxsize=1)
def gateway_locations() -> tuple[Location, ...]:
    conf = GATEWAY_CONF.read_text(encoding="utf-8")
    found: list[Location] = []
    for (header, body, number), is_tls in _blocks(conf):
        if not is_tls:
            continue
        head = _LOCATION_HEAD.match(header)
        if not head:
            raise AssertionError(f"unparsed location at nginx.v9.conf:{number}: {header}")
        text = " ".join([head.group(3), *body])
        proxy = re.search(r"\bproxy_pass\s+([^;\s]+)\s*;", text)
        rewrites = tuple(
            (m.group(1), m.group(2), m.group(3) or "")
            for m in re.finditer(r"\brewrite\s+(\S+)\s+(\S+)(?:\s+(\w+))?\s*;", text)
        )
        found.append(
            Location(
                head.group(1) or "",
                head.group(2),
                proxy.group(1) if proxy else None,
                rewrites,
                number,
            )
        )
    return tuple(found)


def select_location(path: str, locations: tuple[Location, ...]) -> Location | None:
    """nginx's choice: exact, else longest prefix (``^~`` stops), else first regex, else prefix."""
    for loc in locations:
        if loc.modifier == "=" and loc.pattern == path:
            return loc
    prefixes = [
        loc for loc in locations if loc.modifier in ("", "^~") and path.startswith(loc.pattern)
    ]
    longest = max(prefixes, key=lambda loc: len(loc.pattern), default=None)
    if longest is not None and longest.modifier == "^~":
        return longest
    for loc in locations:
        if loc.modifier in ("~", "~*"):
            flags = re.IGNORECASE if loc.modifier == "~*" else 0
            if re.search(loc.pattern, path, flags):
                return loc
    return longest


def _nginx_replacement(replacement: str) -> str:
    return re.sub(r"\$(\d)", r"\\\1", replacement)


@dataclass(frozen=True)
class GatewayRoute:
    upstream: str
    path: str
    location_line: int


def route_through_gateway(path: str) -> GatewayRoute | None:
    loc = select_location(path, gateway_locations())
    if loc is None or loc.proxy_pass is None:
        return None
    target = re.match(r"^https?://([\w-]+)(.*)$", loc.proxy_pass)
    if not target:
        return None
    upstream, uri = target.group(1), target.group(2)
    internal = path
    for regex, replacement, flag in loc.rewrites:
        if re.search(regex, internal):
            internal = re.sub(regex, _nginx_replacement(replacement), internal, count=1)
            if flag in ("break", "last"):
                break
    if "$" in uri:
        # A variable target is the gateway `map` (the seasons canonical path); apply it.
        for public, mapped in web_guard.gateway_rewrites(GATEWAY_CONF.read_text(encoding="utf-8")):
            if internal == public or internal.startswith(public + "/"):
                internal = mapped + internal[len(public) :]
                break
        else:
            return None
    elif uri:
        if loc.modifier == "=":
            internal = uri
        elif loc.modifier in ("", "^~") and not loc.rewrites:
            internal = uri + path[len(loc.pattern) :]
        else:
            return None  # nginx forbids a URI part on a regex location
    return GatewayRoute(upstream, internal, loc.line)


# ── services and their routes ───────────────────────────────────────────────


@lru_cache(maxsize=1)
def upstream_services() -> dict[str, str]:
    """nginx upstream ⇒ inventory service, via the compose service's Dockerfile directory."""
    conf = GATEWAY_CONF.read_text(encoding="utf-8")
    hosts = {
        m.group(1): m.group(2)
        for m in re.finditer(r"upstream\s+(\w+)\s*\{[^}]*?\bserver\s+([\w.-]+):\d+", conf)
    }
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    out: dict[str, str] = {}
    for upstream, host in hosts.items():
        build = (compose.get(host) or {}).get("build")
        dockerfile = build.get("dockerfile", "") if isinstance(build, dict) else ""
        parts = Path(dockerfile).parts
        if len(parts) >= 3 and parts[0] == "services":
            out[upstream] = parts[1]
    return out


@lru_cache(maxsize=1)
def service_routes() -> dict[str, frozenset[tuple[str, str]]]:
    rows = json.loads(ROUTE_INVENTORY.read_text(encoding="utf-8"))
    grouped: dict[str, set[tuple[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["service"], set()).add((row["method"].upper(), row["path"]))
    return {service: frozenset(routes) for service, routes in grouped.items()}


@dataclass(frozen=True)
class Resolution:
    service: str | None
    service_path: str | None
    matched: bool
    why: str


def resolve_call(call: MobileCall) -> Resolution:
    public = call.path + ("/" if call.prefix_only and not call.path.endswith("/") else "")
    routed = route_through_gateway(public)
    if routed is None:
        return Resolution(None, None, False, "the gateway routes this public path nowhere")
    service = upstream_services().get(routed.upstream)
    if service is None:
        return Resolution(None, routed.path, False, f"upstream {routed.upstream} has no service")
    routes = service_routes().get(service, frozenset())
    probe = web_guard.WebPath(call.file, call.line, routed.path, call.method, call.prefix_only)
    matched = web_guard.has_server_route(probe, routes)
    why = "ok" if matched else f"no {call.method or 'ANY'} {routed.path} in {service}"
    return Resolution(service, routed.path, matched, why)


def _unmatched(calls) -> list[tuple[MobileCall, Resolution]]:
    out = []
    for call in calls:
        resolution = resolve_call(call)
        if not resolution.matched:
            out.append((call, resolution))
    return out


# ── the guard ───────────────────────────────────────────────────────────────


def test_no_dart_file_is_lexically_unreadable():
    _, unreadable = mobile_calls()
    assert not unreadable, (
        "a Dart file could not be lexed, so its calls were not checked (fail closed, not "
        f"skipped): {list(unreadable)}"
    )


def test_scan_reaches_the_mobile_api_surface():
    calls, _ = mobile_calls()
    assert DART_LIB.is_dir(), "mobile/sahool_app/lib moved: the guard is pointed at nothing"
    # Floors well below today's measure: an empty or collapsed scan means a blind scanner,
    # not a mobile app that stopped calling the platform.
    assert len(calls) >= 150, f"only {len(calls)} mobile calls found: the scanner went blind"
    with_method = [c for c in calls if c.method]
    assert len(with_method) >= 120, f"only {len(with_method)} calls have a method attributed"
    files = {c.file for c in calls}
    for owner in (
        "mobile/sahool_app/lib/core/network/api_client.dart",
        "mobile/sahool_app/lib/features/auth/data/auth_api.dart",
        "mobile/sahool_app/lib/features/fields/data/fields_api.dart",
        "mobile/sahool_app/lib/features/farm_book/data/farm_book_api.dart",
    ):
        assert owner in files, f"no call extracted from {owner}"


def assert_every_call_has_a_backend(calls) -> None:
    unmatched = [
        (c, r) for c, r in _unmatched(calls) if c.key not in KNOWN_MOBILE_CALLS_WITHOUT_BACKEND
    ]
    detail = "\n".join(
        f"  {c.file}:{c.line}  {c.method or 'ANY'} {c.path}  ⇒ {r.why}" for c, r in unmatched
    )
    assert not unmatched, (
        "mobile HTTP call(s) that no backend handler serves (gateway nginx/nginx.v9.conf ⇒ "
        "service ⇒ route_inventory.generated.json). Build the handler and regenerate the "
        "inventory, fix the path, or register the gap in KNOWN_MOBILE_CALLS_WITHOUT_BACKEND "
        f"with a reason and an owner (MOBILE-BACKEND-CONTRACT-01):\n{detail}"
    )


def test_every_mobile_call_has_a_backend_handler():
    assert_every_call_has_a_backend(mobile_calls()[0])


def test_known_gaps_have_reasons_and_are_not_stale():
    calls, _ = mobile_calls()
    present = {c.key for c in calls}
    unmatched = {c.key for c, _ in _unmatched(calls)}
    for key, entry in KNOWN_MOBILE_CALLS_WITHOUT_BACKEND.items():
        assert entry.get("reason", "").strip(), f"allowlisted gap without a reason: {key}"
        assert entry.get("owner", "").strip(), f"allowlisted gap without an owner note: {key}"
    stale = sorted(set(KNOWN_MOBILE_CALLS_WITHOUT_BACKEND) - (present & unmatched))
    assert not stale, (
        "allowlisted mobile gaps that no longer exist or now reach a handler; delete them so "
        f"the list only shrinks: {stale}"
    )


def test_mobile_auth_calls_reach_the_auth_service():
    """The real auth contract: ``/auth/*`` via the gateway to auth's ``/v1/auth/*``.

    Not ``/api/v1/auth``: that prefix lands on the platform, which mirrors only login, me,
    logout and signup, so a refresh or MFA call there would 404 and a login there would
    mint tokens the auth service's refresh never issued.
    """
    calls, _ = mobile_calls()
    auth_calls = [c for c in calls if re.match(r"^/(?:api/v1/)?auth/", c.path)]
    paths = {(c.method, c.path) for c in auth_calls}
    for expected in (("POST", "/auth/login"), ("POST", "/auth/refresh"), ("POST", "/auth/logout")):
        assert expected in paths, f"auth call {expected} not extracted: {sorted(paths)}"
    wrong = []
    for call in auth_calls:
        resolution = resolve_call(call)
        if resolution.service != "auth":
            wrong.append(
                f"{call.file}:{call.line} {call.method} {call.path} ⇒ {resolution.service}"
            )
    assert not wrong, "mobile auth call(s) that do not reach the auth service:\n  " + "\n  ".join(
        wrong
    )


# ── witnesses: the extractor and matcher reject what they must ─────────────

_BOGUS_DART = r"""
class BogusApi {
  static const _base = '/api/v1/farm-book';
  String _f(String id) => '/api/v1/fields/${Uri.encodeComponent(id)}';
  // _client.get('/api/v1/commented/out/call');
  /* '/api/v1/also/commented' */
  Future<void> run(String id) async {
    await _client.get('/api/v1/definitely-not-a-route/$id');
    await _client.post('$_base/no-such-ledger');
    await _client.send('PATCH', '${_f(id)}/no-such-thing');
    await _client.delete('/api/v1/fields');
    await _client.post('/auth/no-such-auth-endpoint');
  }
}
"""


def test_extractor_reads_interpolation_constants_and_ignores_comments():
    found = scan_dart(_BOGUS_DART, rel="bogus.dart")
    pairs = sorted((c.method, c.path) for c in found if c.method)
    assert pairs == [
        ("DELETE", "/api/v1/fields"),
        ("GET", "/api/v1/definitely-not-a-route/{}"),
        ("PATCH", "/api/v1/fields/{}/no-such-thing"),
        ("POST", "/api/v1/farm-book/no-such-ledger"),
        ("POST", "/auth/no-such-auth-endpoint"),
    ], pairs
    assert not any("commented" in c.path for c in found)
    # The constants used as a base are kept as prefixes, not as endpoints.
    assert {c.path for c in found if c.prefix_only} == {"/api/v1/farm-book", "/api/v1/fields/{}"}


def test_negative_control_bogus_calls_are_rejected():
    """Each injected call is unmatched; the guard would go red on any of them."""
    found = [c for c in scan_dart(_BOGUS_DART, rel="bogus.dart") if c.method]
    rejected = {(c.method, c.path) for c, _ in _unmatched(found)}
    assert rejected == {(c.method, c.path) for c in found}, rejected


def test_negative_control_the_guard_fails_on_an_injected_call():
    """The real scan plus one fake call: the very assertion the guard runs goes red."""
    injected = MobileCall(
        "mobile/sahool_app/lib/features/fields/data/fields_api.dart",
        1,
        "/api/v1/fields/{}/no-such-capability",
        "GET",
        False,
    )
    with pytest.raises(AssertionError, match="no-such-capability"):
        assert_every_call_has_a_backend((*mobile_calls()[0], injected))


def test_real_shapes_are_accepted():
    source = r"""
    Future<void> ok(String id, String f) async {
      await _client.get('/api/v1/fields/$id');
      await _client.send('POST', '/auth/login', data: {});
      await _client.get('/api/raster/v1/fields/$id/timeseries');
      await _client.post('/api/edge/v1/inference/pest-detect');
    }
    """
    found = scan_dart(source, rel="ok.dart")
    assert len(found) == 4
    assert not _unmatched(found), [(c.path, r.why) for c, r in _unmatched(found)]
    # The gateway hop is real: raster's prefix is stripped, auth is rewritten to /v1/auth.
    by_path = {c.path: resolve_call(c) for c in found}
    assert by_path["/api/raster/v1/fields/{}/timeseries"].service == "raster-service"
    assert by_path["/api/raster/v1/fields/{}/timeseries"].service_path == "/v1/fields/{}/timeseries"
    assert (by_path["/auth/login"].service, by_path["/auth/login"].service_path) == (
        "auth",
        "/v1/auth/login",
    )


def test_a_literal_segment_never_satisfies_a_parameter_and_method_matters():
    # GET /api/v1/fields/{field_id} exists; a literal "import" segment must not ride on it,
    # and DELETE /api/v1/fields (the collection) must not ride on GET/POST.
    literal = MobileCall("x.dart", 1, "/api/v1/fields/import-nothing", "GET", False)
    wrong_method = MobileCall("x.dart", 1, "/api/v1/fields", "DELETE", False)
    assert not resolve_call(literal).matched
    assert not resolve_call(wrong_method).matched
    assert resolve_call(MobileCall("x.dart", 1, "/api/v1/fields/{}", "GET", False)).matched
