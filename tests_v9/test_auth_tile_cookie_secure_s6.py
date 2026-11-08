"""S6: the ``sahool_at`` cookie (a full access JWT) is Secure unless local dev says otherwise.

Audit S6 (2026-11-01). On Railway TLS ends at the edge; the frontend gateway forwards
``X-Forwarded-Proto $scheme`` = ``http`` (frontend/nginx.conf, ``location /auth/``), so the
old ``auto`` mode — Secure only when the scheme said https — issued the JWT cookie without
``Secure`` in production. The fix: ``auto`` is Secure unless ``SAHOOL_ENV`` names local dev,
and only an explicit ``AUTH_COOKIE_SECURE=0`` (or local dev on plain HTTP) drops it.

These run the real ``set_tile_auth_cookie`` on a real Starlette response and read the
emitted ``Set-Cookie`` — not the source text. The HSTS check reads the gateway config's
server block and both document locations (a location with any ``add_header`` does not
inherit the server's headers).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
AUTH_DIR = ROOT / "services" / "auth"
HSTS = 'add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;'

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_module import load_service_main  # noqa: E402


def _request(forwarded_proto: str | None, scheme: str = "http"):
    from starlette.requests import Request

    headers = [(b"x-forwarded-proto", forwarded_proto.encode())] if forwarded_proto else []
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": scheme,
            "path": "/v1/auth/login",
            "server": ("sahool-auth", 8000),
            "headers": headers,
        }
    )


@pytest.fixture
def issue(monkeypatch):
    main = load_service_main(str(AUTH_DIR), required_attrs=("set_tile_auth_cookie",))

    def _issue(mode: str | None, env: str | None, forwarded_proto: str | None) -> str:
        from starlette.responses import Response

        if mode is None:
            monkeypatch.delenv("AUTH_COOKIE_SECURE", raising=False)
            mode = "auto"  # the module-level default when the variable is unset
        monkeypatch.setattr(main, "AUTH_COOKIE_SECURE_MODE", mode)
        if env is None:
            monkeypatch.delenv("SAHOOL_ENV", raising=False)
        else:
            monkeypatch.setenv("SAHOOL_ENV", env)
        response = Response()
        main.set_tile_auth_cookie(response, "header.payload.sig", _request(forwarded_proto))
        cookie = response.headers["set-cookie"]
        assert cookie.startswith(f"{main.AUTH_TILE_COOKIE_NAME}=")
        return cookie.lower()

    return _issue


@pytest.mark.parametrize(
    ("mode", "env", "forwarded_proto"),
    [
        # Railway as measured: production, edge-terminated TLS, gateway says http.
        ("auto", "production", "http"),
        # Default config: nothing set at all.
        (None, None, None),
        (None, None, "http"),
        # Any non-dev tier, and an empty variable, stays Secure (fail-safe).
        ("auto", "staging", "http"),
        ("auto", "prod", None),
        ("", "production", "http"),
        # Forcing on is honoured everywhere, dev included.
        ("1", "development", "http"),
    ],
)
def test_cookie_is_secure_outside_explicit_local_dev(issue, mode, env, forwarded_proto):
    cookie = issue(mode, env, forwarded_proto)
    assert "; secure" in cookie, cookie
    assert "; httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie


@pytest.mark.parametrize(
    ("mode", "env", "forwarded_proto"),
    [
        # The explicit dev opt-out (docker-compose.dev.yml) drops Secure in any env.
        ("0", "development", None),
        ("0", "production", "http"),
        # Local compose on plain HTTP :3003 (SAHOOL_ENV defaults to development there).
        ("auto", "development", "http"),
        ("auto", "local", None),
    ],
)
def test_dev_flag_allows_non_secure_cookie_for_plain_http(issue, mode, env, forwarded_proto):
    cookie = issue(mode, env, forwarded_proto)
    assert "; secure" not in cookie, cookie
    assert "; httponly" in cookie


def test_local_dev_behind_https_proxy_is_still_secure(issue):
    # Proxy trust is not widened: in dev the forwarded scheme can only upgrade to Secure.
    assert "; secure" in issue("auto", "development", "https")


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


def _server_level(block: str) -> str:
    """Directives directly in the server block (nested location bodies removed)."""
    out, depth = [], 0
    for ch in block:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def test_railway_gateway_sends_hsts_on_server_and_document_locations():
    raw = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    server = _block(raw, "server {")
    assert HSTS in _server_level(server)
    # These locations declare their own add_header, so they inherit nothing.
    assert HSTS in _block(raw, "location = /index.html {")
    assert HSTS in _block(raw, "location = /realtime-call/ {")
