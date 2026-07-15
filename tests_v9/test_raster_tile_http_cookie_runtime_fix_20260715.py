from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_tile_cookie_secure_defaults_to_auto_and_uses_forwarded_proto():
    src = read("services/auth/main.py")
    assert 'AUTH_COOKIE_SECURE_MODE = os.getenv("AUTH_COOKIE_SECURE", "auto")' in src
    assert "def _tile_cookie_secure(request)" in src
    assert 'request.headers.get("x-forwarded-proto"' in src
    assert 'return scheme == "https"' in src
    assert "secure=_tile_cookie_secure(request)" in src


def test_all_session_issuers_pass_request_to_cookie_helper():
    session = read("services/auth/routers/session.py")
    registration = read("services/auth/routers/registration.py")
    invitations = read("services/auth/routers/invitations.py")
    assert session.count("main.set_tile_auth_cookie(response, token, request)") >= 2
    assert "main.clear_tile_auth_cookie(response, request)" in session
    assert "main.set_tile_auth_cookie(response, token, request)" in registration
    assert "main.set_tile_auth_cookie(response, token, request)" in invitations


def test_compose_local_http_is_auto_not_forced_secure():
    compose = read("docker-compose.v9.yml")
    env = read(".env.example")
    assert "AUTH_COOKIE_SECURE: ${AUTH_COOKIE_SECURE:-auto}" in compose
    assert "AUTH_COOKIE_SECURE=auto" in env


def test_raster_proxy_forwards_verified_token_source_downstream():
    dev = read("frontend/nginx.conf")
    prod = read("nginx/nginx.v9.conf")
    assert "proxy_set_header   Authorization     $fwd_auth;" in dev
    assert "proxy_set_header Authorization $fwd_auth;" in prod
