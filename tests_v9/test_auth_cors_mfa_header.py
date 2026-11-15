"""C-39: the auth service's CORS policy admits the step-up MFA header for allowed origins only.

``frontend/src/services/api/auth.ts`` sends ``X-MFA-Code`` on ``changeUserRole`` and
``deactivateUser``. A browser on an allowed origin that calls the auth service directly
(cross-origin) must pass the OPTIONS preflight for that header; a disallowed origin must
not, and the policy keeps explicit origins with credentials (no wildcard).
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED = "https://app.sahool.example"
DENIED = "https://evil.example"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from tests_v9.service_module import purge_generic_modules

    mp = pytest.MonkeyPatch()
    mp.setenv("CORS_ORIGINS", ALLOWED)
    mp.setenv("SAHOOL_ENV", "development")
    mp.setenv("JWT_SECRET", os.getenv("JWT_SECRET") or "z" * 48)
    auth_dir = os.path.join(ROOT, "services/auth")
    saved_path = list(sys.path)
    # This fixture rebinds ``main`` and purges the generic service modules. Restore both:
    # a later file that loaded auth at collection time and resolves ``import main`` at call
    # time (``mfa_runtime._main()``) would otherwise read this module, whose pool never started.
    saved_modules = dict(sys.modules)
    for p in (ROOT, auth_dir):
        while p in sys.path:
            sys.path.remove(p)
    sys.path[:0] = [auth_dir, ROOT]
    purge_generic_modules()
    spec = importlib.util.spec_from_file_location(
        "auth_main_cors_c39", os.path.join(auth_dir, "main.py")
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["auth_main_cors_c39"] = m
    sys.modules["main"] = m
    try:
        spec.loader.exec_module(m)
        # No ``with``: the lifespan (DB/Redis) is not started; CORS preflight is answered
        # by the middleware before any route or dependency runs.
        yield TestClient(m.app)
    finally:
        mp.undo()
        sys.path[:] = saved_path
        for name in [n for n in sys.modules if n not in saved_modules]:
            del sys.modules[name]
        sys.modules.update(saved_modules)


def _preflight(client, origin, headers="authorization,x-mfa-code"):
    return client.options(
        "/v1/auth/users/1/role",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": headers,
        },
    )


def test_allowed_origin_preflight_admits_the_mfa_header(client):
    r = _preflight(client, ALLOWED)
    assert r.status_code == 200, r.text
    allowed = {h.strip().lower() for h in r.headers["access-control-allow-headers"].split(",")}
    assert {"authorization", "x-mfa-code"} <= allowed
    assert r.headers["access-control-allow-origin"] == ALLOWED
    assert r.headers.get("access-control-allow-credentials") == "true"


def test_disallowed_origin_preflight_is_refused(client):
    r = _preflight(client, DENIED)
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers


def test_unlisted_header_is_still_refused(client):
    r = _preflight(client, ALLOWED, headers="authorization,x-forwarded-user")
    assert r.status_code == 400
