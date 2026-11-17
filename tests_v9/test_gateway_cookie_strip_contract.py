"""No gateway location forwards the browser's Cookie header upstream (GATEWAY-COOKIE-FORWARD-01).

The fault: ``frontend/nginx.conf`` is the public Railway gateway, and nginx forwards every
client header unless a location replaces it. ``location /api/`` (and most other proxied
blocks) sent the browser's ``Cookie`` header, including the HttpOnly ``sahool_at`` JWT, to the
platform and to every service. None of them reads a cookie: the platform and the services
authenticate with ``Authorization: Bearer`` only, and auth sets ``sahool_at`` but never reads
it back. The only reader is the gateway itself, which turns ``$cookie_sahool_at`` into a
Bearer header for ``<img>`` tiles and inside the auth subrequests. ``$cookie_*`` reads the
client request, so clearing the upstream header leaves that bridge working.

The rule checked here, for each gateway the repository ships:

* ``frontend/nginx.conf``: every location with ``proxy_pass`` sets ``proxy_set_header Cookie
  "";`` itself (every block has its own ``proxy_set_header`` lines, so nothing is inherited).
* ``nginx/nginx.v9.conf`` (compose): ``proxy_params.conf`` clears Cookie; a location either
  includes it, clears Cookie itself, or sets no ``proxy_set_header`` at all and inherits the
  http-level include.
* the Helm gateway: same, with its own ``proxy_params.conf``.

A location that genuinely needs the cookie upstream goes in ``COOKIE_REQUIRED`` with the
reader named. It is empty: no service in ``services/`` reads ``request.cookies``, which
``test_no_service_reads_a_request_cookie`` keeps true. Static scan, no nginx; the request-level
proof (the upstream receives no cookie) is ``frontend/tests/test_nginx_runtime.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "nginx.conf"
V9 = ROOT / "nginx" / "nginx.v9.conf"
V9_PARAMS = ROOT / "nginx" / "proxy_params.conf"
HELM_ROUTES = ROOT / "helm" / "sahool" / "files" / "gateway" / "routes.conf"
HELM_PARAMS = ROOT / "helm" / "sahool" / "files" / "gateway" / "proxy_params.conf"

#: ``"<modifier> <path>"`` -> the upstream code that reads a cookie. Empty on purpose.
COOKIE_REQUIRED: dict[str, str] = {}

_HEADER = re.compile(r"(?m)^\s*location\s+((?:=|\^~|~\*|~)\s+)?(\S+)\s*\{")
_CLEARS = re.compile(r'(?m)^\s*proxy_set_header\s+Cookie\s+""\s*;')


def _strip_comments(text: str) -> str:
    return re.sub(r"(?m)#[^\n]*", "", text)


def _location_blocks(text: str) -> list[tuple[str, str]]:
    """``("<modifier> <path>", own body)`` for every location, in file order.

    A list, not a dict: the same location in two server blocks is two entries, so a second
    ``location /api/`` cannot hide behind the first. A nested location's text is removed
    from its parent's body, so a parent cannot pass on a child's ``Cookie`` clear (and the
    child is checked on its own).
    """
    text = _strip_comments(text)
    spans: list[tuple[str, int, int]] = []  # key, index of "{", index of matching "}"
    for match in _HEADER.finditer(text):
        key = f"{(match[1] or '').strip()} {match[2]}".strip()
        depth, start = 0, text.index("{", match.start())
        for index in range(start, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    spans.append((key, start, index))
                    break
        else:
            raise AssertionError(f"unbalanced braces after location {key}")
    headers = {start: text.rindex("location", 0, start) for _, start, _ in spans}
    blocks = []
    for key, start, end in spans:
        body, cursor = [], start + 1
        for _, inner_start, inner_end in spans:
            if start < inner_start < end and headers[inner_start] >= cursor:
                body.append(text[cursor : headers[inner_start]])
                cursor = inner_end + 1
        body.append(text[cursor:end])
        blocks.append((key, "".join(body)))
    return blocks


def _locations(text: str) -> dict[str, list[str]]:
    """``"<modifier> <path>"`` -> the own body of every block with that key."""
    found: dict[str, list[str]] = {}
    for key, body in _location_blocks(text):
        found.setdefault(key, []).append(body)
    return found


def _proxied_blocks(text: str) -> list[tuple[str, str]]:
    return [(k, v) for k, v in _location_blocks(text) if re.search(r"\bproxy_pass\s", v)]


def _proxied(text: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for key, body in _proxied_blocks(text):
        found.setdefault(key, []).append(body)
    return found


def frontend_offenders(text: str) -> list[str]:
    return sorted(
        key
        for key, body in _proxied_blocks(text)
        if key not in COOKIE_REQUIRED and not _CLEARS.search(body)
    )


_INCLUDES_PARAMS = re.compile(r"(?m)^\s*include\s+\S*proxy_params\.conf\s*;")


def included_offenders(text: str) -> list[str]:
    """Locations that neither clear Cookie, include proxy_params.conf, nor inherit it."""
    offenders = []
    for key, body in _proxied_blocks(text):
        if key in COOKIE_REQUIRED or _CLEARS.search(body) or _INCLUDES_PARAMS.search(body):
            continue
        if "proxy_set_header" not in body:
            continue  # inherits the enclosing level, checked by the caller
        offenders.append(key)
    return sorted(offenders)


def _http_level_include(text: str) -> bool:
    """True when ``include ...proxy_params.conf;`` sits directly in the ``http`` block."""
    text = _strip_comments(text)
    depth = 0
    for index, char in enumerate(text):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif depth == 1 and _INCLUDES_PARAMS.match(text, index):
            return True
    return False


def test_the_scan_sees_the_proxied_locations() -> None:
    frontend = _proxied(FRONTEND.read_text(encoding="utf-8"))
    assert len(frontend) >= 25, f"frontend proxied-location scan looks empty: {sorted(frontend)}"
    for key in ("/api/", "~ ^/api/v1/gis/cloud-native/rasters/[^/]+/tiles/", "= /_auth_verify"):
        assert key in frontend, f"{key} not found among proxied locations: {sorted(frontend)}"
    assert len(_proxied(V9.read_text(encoding="utf-8"))) >= 30, "v9 proxied scan looks empty"
    assert len(_proxied(HELM_ROUTES.read_text(encoding="utf-8"))) >= 5, "helm scan looks empty"


def test_every_railway_gateway_location_clears_the_cookie() -> None:
    offenders = frontend_offenders(FRONTEND.read_text(encoding="utf-8"))
    assert not offenders, (
        "frontend/nginx.conf locations forward the browser Cookie (with the sahool_at JWT) "
        f'upstream; add `proxy_set_header Cookie "";`: {offenders}'
    )


def test_the_cookie_bridge_still_reads_the_client_cookie() -> None:
    """Clearing the upstream header must not remove the gateway's own cookie reads."""
    frontend = _locations(FRONTEND.read_text(encoding="utf-8"))
    for key in (
        "~ ^/api/v1/gis/cloud-native/rasters/[^/]+/tiles/",
        "= /_auth_verify",
        "^~ /api/raster/",
    ):
        assert key in frontend, f"{key}: bridge location not found"
        for body in frontend[key]:
            assert 'set $fwd_auth "Bearer $cookie_sahool_at";' in body, (
                f"{key}: the cookie->Bearer bridge is gone"
            )
            assert _CLEARS.search(body), f"{key}: forwards the cookie after bridging it"


def test_compose_gateway_clears_the_cookie_everywhere() -> None:
    assert _CLEARS.search(V9_PARAMS.read_text(encoding="utf-8")), (
        "nginx/proxy_params.conf must clear Cookie for every location that includes it"
    )
    text = V9.read_text(encoding="utf-8")
    assert _http_level_include(text), (
        "the http-level proxy_params include (inherited by bare locations) is gone"
    )
    offenders = included_offenders(text)
    assert not offenders, f"nginx.v9.conf locations forward the browser Cookie: {offenders}"


def test_helm_gateway_clears_the_cookie_everywhere() -> None:
    assert _CLEARS.search(HELM_PARAMS.read_text(encoding="utf-8")), (
        "helm gateway proxy_params.conf must clear Cookie"
    )
    offenders = included_offenders(HELM_ROUTES.read_text(encoding="utf-8"))
    assert not offenders, f"helm gateway routes forward the browser Cookie: {offenders}"


def test_cookie_required_entries_are_real_locations() -> None:
    frontend = _proxied(FRONTEND.read_text(encoding="utf-8"))
    for key, reader in COOKIE_REQUIRED.items():
        assert key in frontend, f"COOKIE_REQUIRED names {key!r}, not a proxied location"
        assert reader.strip(), f"COOKIE_REQUIRED[{key!r}] must name the upstream cookie reader"


def test_no_service_reads_a_request_cookie() -> None:
    """The premise of the rule: if a service starts reading a cookie, decide it here."""
    pattern = re.compile(r"\.cookies\b(?!\s*=)|\bCookie\(")
    readers = []
    for base in ("services", "agents", "bots"):
        for path in (ROOT / base).rglob("*.py"):
            parts = set(path.relative_to(ROOT).parts)
            if parts & {"tests", "node_modules", ".venv"} or path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(text):
                readers.append(str(path.relative_to(ROOT)))
    assert not readers, (
        "service code reads a request cookie; if it is reached through a gateway, list that "
        f"location in COOKIE_REQUIRED with the reader, else drop the read: {readers}"
    )


def test_the_check_fails_on_a_location_that_forwards_the_cookie() -> None:
    """Negative control: the same scan flags a block without the clear."""
    sample = """
    location /api/ {
        proxy_pass http://frontend_platform/api/;
        proxy_set_header Host $host;
    }
    location /auth/ {
        proxy_pass http://frontend_auth;
        proxy_set_header Cookie "";
    }
    location = /healthz { return 200 "ok"; }
    """
    assert frontend_offenders(sample) == ["/api/"], "scan missed a cookie-forwarding block"
    commented = sample.replace(
        'proxy_set_header Cookie "";',
        '# proxy_set_header Cookie "";\n        proxy_set_header X "";',
    )
    assert frontend_offenders(commented) == ["/api/", "/auth/"], "a commented-out clear counted"
    assert included_offenders(sample) == ["/api/"], (
        "included-params scan missed a block with its own headers and no include"
    )


def test_a_duplicate_or_nested_location_cannot_hide_a_forwarding_block() -> None:
    """A second ``/api/`` in another server, or a child inside a parent, is checked on its own."""
    duplicate = """
    server {
        location /api/ {
            proxy_pass http://frontend_platform/api/;
            proxy_set_header Host $host;
        }
    }
    server {
        location /api/ {
            proxy_pass http://frontend_platform/api/;
            proxy_set_header Cookie "";
        }
    }
    """
    assert frontend_offenders(duplicate) == ["/api/"], (
        "the later /api/ block hid the earlier one that forwards the cookie"
    )
    nested = """
    location /api/ {
        proxy_pass http://frontend_platform/api/;
        proxy_set_header Host $host;
        location /api/inner/ {
            proxy_pass http://frontend_platform/api/inner/;
            proxy_set_header Cookie "";
        }
    }
    location /x/ {
        location /x/y/ {
            proxy_pass http://frontend_platform/x/y/;
            proxy_set_header Host $host;
        }
        proxy_set_header Cookie "";
    }
    """
    assert frontend_offenders(nested) == ["/api/", "/x/y/"], (
        "a parent location took credit for its child's Cookie clear, or the reverse"
    )
