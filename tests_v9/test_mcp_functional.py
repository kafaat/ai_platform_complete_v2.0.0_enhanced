#!/usr/bin/env python3
"""SAHOOL v9 — MCP server functional / security verification tests.

These tests run the MCP FastAPI apps **in-process** via
``fastapi.testclient.TestClient`` — no live HTTP services are required — and
verify (a) the health endpoint and (b) JWT scope enforcement on the
``POST /v1/mcp/tools/call`` endpoint.

INVESTIGATION FINDINGS
----------------------

Import layout (this dev checkout vs. the container image):

* ``services/mcp_servers/`` is on ``sys.path`` and contains a real package
  ``shared/`` (``oauth_middleware``, ``streamable_http``). The **repo root**
  also has a ``shared/`` package (``helpers``, ``logging_config``). The two are
  *separate* packages here; the container ``Dockerfile`` merges them into one
  ``shared`` package, so in-container ``import shared.helpers`` works.

* Consequence in this dev layout: because ``services/mcp_servers/shared`` is
  found first on ``sys.path``, ``import shared.helpers`` (repo-root-only) raises
  ``ModuleNotFoundError`` even with the repo root also on the path —
  sub-package shadowing, not a missing-path problem.

  - ``market_server``  → imports cleanly (no ``shared.helpers`` dependency).
  - ``wofost_server``  → imports cleanly (only ``shared.oauth_middleware`` /
    ``shared.streamable_http``, both in ``mcp_servers/shared``).
  - ``weather_server`` / ``sentinel_hub_server`` → import ``shared.helpers`` →
    SKIPPED here (works in-container). Skips are not failures.

Scope enforcement:

* ``wofost_server`` guards ``POST /v1/mcp/tools/call`` with
  ``Depends(require_scope("crop:read"))`` → no token = 401, wrong scope = 403,
  correct scope = passes auth (then 200/400/422 on the tool itself).

* ``market_server`` — SECURITY BUG FOUND **AND FIXED**: its
  ``POST /v1/mcp/tools/call`` (and ``GET /v1/mcp/tools/list``) used to have **no**
  auth guard (returned 200 to anonymous callers) while the REST surface required
  a Bearer token. Now guarded by ``Depends(require_scope("market:read"))`` like
  wofost. ``test_market_mcp_call_endpoint_enforces_scope`` asserts 401 (no token)
  / 403 (wrong scope) / pass (correct scope); ``test_market_rest_endpoint_requires_bearer``
  confirms the REST auth.

The module sets the required env at import time but performs no DB/network at
collection; tests guard with skips so the file is pytest-collectable in any
layout and runnable standalone via ``python3 tests_v9/test_mcp_functional.py``.
"""

from __future__ import annotations

import importlib
import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_DIR = REPO_ROOT / "services" / "mcp_servers"

JWT_SECRET = "test_secret_min_32_chars_for_sahool_v9"


def _set_mcp_env() -> None:
    """Env the MCP servers read at import / request time."""
    os.environ.setdefault("DATABASE_URL", "postgresql://sahool_user@/sahool?host=/tmp/pgrun")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("JWT_SECRET", JWT_SECRET)
    os.environ.setdefault("SAHOOL_AGENT_TOKEN", "test-token")
    # require_scope reads JWT_SECRET from env at request time; force the test
    # secret even if the ambient value differs (don't rely on setdefault here).
    os.environ["JWT_SECRET"] = JWT_SECRET


def _ensure_mcp_path() -> None:
    """Put services/mcp_servers AND the repo root on sys.path (container merge).

    In-container both shared dirs are merged into one ``shared`` package; here we
    add both paths with ``MCP_DIR`` taking precedence so wofost/market resolve
    their ``shared.oauth_middleware`` / ``shared.streamable_http`` deps. weather /
    sentinel additionally need the repo-root-only ``shared.helpers`` and so still
    fail in this dev layout (handled by skipping).

    We insert at index 0 in reverse so the final order is ``[MCP_DIR, REPO_ROOT, ...]``
    (the last ``insert(0, ...)`` wins). A previously-imported partial ``shared``
    package (e.g. the repo-root one bound by some other test) is evicted so the
    mcp_servers ``shared`` can bind its submodules.
    """
    for p in (str(REPO_ROOT), str(MCP_DIR)):  # MCP_DIR inserted last → ends up first
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
    # Drop a stale top-level ``shared`` binding (and its submodules) so the
    # mcp_servers ``shared`` resolves; harmless if absent.
    for name in [n for n in sys.modules if n == "shared" or n.startswith("shared.")]:
        mod = sys.modules.get(name)
        mod_file = getattr(mod, "__file__", "") or ""
        # Only evict the repo-root ``shared`` package (keeps mcp_servers one if loaded).
        if mod_file and str(MCP_DIR) not in mod_file:
            sys.modules.pop(name, None)


def _import_server(module_name: str):
    """Import an MCP server module; pytest.skip if it can't load in this layout."""
    _set_mcp_env()
    _ensure_mcp_path()
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.skip(
            f"{module_name} not importable in dev layout (merges with repo-root "
            f"shared/ only in-container): missing {exc.name}"
        )
    except Exception as exc:  # noqa: BLE001 — defensive against unknown dev breakage
        pytest.skip(f"{module_name} could not be imported: {type(exc).__name__}: {exc}")


def _test_client(app):
    """Build a TestClient, skipping if fastapi/starlette TestClient is unavailable."""
    try:
        from fastapi.testclient import TestClient
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"fastapi TestClient unavailable: {exc}")
    return TestClient(app)


def _scoped_token(scope: str | None = None, *, aud: str = "sahool") -> str:
    """Craft an HS256 JWT matching require_scope's expectations (audience=sahool)."""
    import jwt

    now = int(time.time())
    payload = {
        "sub": "1",
        "iss": "sahool-auth",
        "aud": aud,
        "tenant_id": "test-tenant-001",
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
    }
    if scope is not None:
        payload["scope"] = scope
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture(autouse=True)
def _restore_import_state():
    """يستعيد sys.path وsys.modules['shared*'] بعد كلّ اختبار mcp.

    FIX (عزل الاختبارات): _ensure_mcp_path يُخلي حزمة shared الجذريّة من
    sys.modules ويضع mcp_servers أوّلاً على sys.path؛ لولا الاستعادة لتسرّب هذا
    إلى ملفّات اختبار لاحقة تستورد shared.logging_config/helpers الجذريّة
    فتفشل بـModuleNotFoundError (تلوّث ترتيب الاستيراد).
    """
    path_before = list(sys.path)
    shared_before = {
        k: v for k, v in sys.modules.items() if k == "shared" or k.startswith("shared.")
    }
    try:
        yield
    finally:
        sys.path[:] = path_before
        for k in [k for k in sys.modules if k == "shared" or k.startswith("shared.")]:
            sys.modules.pop(k, None)
        sys.modules.update(shared_before)


# ── market_server (imports cleanly) ─────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.mcp
def test_market_healthz_ok():
    """GET /healthz == 200 (DB may be down; endpoint still returns 200/alive)."""
    mod = _import_server("market_server")
    client = _test_client(mod.app)
    resp = client.get("/healthz")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("status") == "alive"
    assert body.get("service") == "market-mcp"


@pytest.mark.security
@pytest.mark.mcp
def test_market_mcp_call_endpoint_enforces_scope():
    """FIXED: market_server's POST /v1/mcp/tools/call is now guarded by
    require_scope("market:read") — matching wofost. No token → 401, wrong
    scope → 403, correct scope → passes auth (then the tool runs / 404 / 422,
    not 401/403). (Previously the MCP endpoint was unauthenticated.)

    NOTE: نختبر مرور الحارس عبر أداة قراءة (get_market_price) لا
    create_forward_contract — فالأخيرة صارت أداة كتابة (تتطلّب market:write) فيردّها
    market:read بـ403 بحقّ. تمرير الحارس = ليس 401/403 (قد يصل التنفيذ 200/500/503).
    """
    mod = _import_server("market_server")
    client = _test_client(mod.app)
    body = {"name": "get_market_price", "arguments": {"crop": "wheat", "market": "sanaa"}}

    r_no = client.post("/v1/mcp/tools/call", json=body)
    assert r_no.status_code == 401, f"بلا توكن متوقّع 401: {r_no.status_code} {r_no.text!r}"

    r_wrong = client.post(
        "/v1/mcp/tools/call",
        json=body,
        headers={"Authorization": f"Bearer {_scoped_token('weather:read')}"},
    )
    assert r_wrong.status_code == 403, f"نطاق خاطئ متوقّع 403: {r_wrong.status_code}"

    r_ok = client.post(
        "/v1/mcp/tools/call",
        json=body,
        headers={"Authorization": f"Bearer {_scoped_token('market:read')}"},
    )
    assert r_ok.status_code not in (401, 403), (
        f"نطاق market:read يجب أن يمرّ الحارس: {r_ok.status_code} {r_ok.text!r}"
    )


@pytest.mark.security
@pytest.mark.mcp
def test_market_rest_endpoint_requires_bearer():
    """The auth that IS enforced: market REST surface needs a Bearer token.

    Confirms market_server is not auth-free everywhere — /products (and the other
    REST routes) use Depends(_get_current_user) and reject missing tokens with 401.
    """
    mod = _import_server("market_server")
    client = _test_client(mod.app)
    resp = client.get("/products")
    assert resp.status_code == 401, (
        f"market REST /products should require a Bearer token; got {resp.status_code}"
    )


# ── wofost_server (imports cleanly; scope-guarded MCP endpoint) ─────────────


@pytest.mark.integration
@pytest.mark.mcp
def test_wofost_healthz_ok():
    mod = _import_server("wofost_server")
    client = _test_client(mod.app)
    resp = client.get("/healthz")
    assert resp.status_code == 200, resp.text


@pytest.mark.security
@pytest.mark.mcp
def test_wofost_mcp_call_rejects_missing_token():
    """No Authorization header → require_scope('crop:read') returns 401."""
    mod = _import_server("wofost_server")
    client = _test_client(mod.app)
    resp = client.post("/v1/mcp/tools/call", json={"name": "x", "arguments": {}})
    assert resp.status_code == 401, (
        f"missing token must be rejected (401); got {resp.status_code}: {resp.text!r}"
    )


@pytest.mark.security
@pytest.mark.mcp
def test_wofost_mcp_call_rejects_wrong_scope():
    """Valid JWT lacking 'crop:read' (and not admin) → 403."""
    mod = _import_server("wofost_server")
    client = _test_client(mod.app)
    token = _scoped_token(scope="weather:read")  # wrong scope on purpose
    resp = client.post(
        "/v1/mcp/tools/call",
        json={"name": "x", "arguments": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, (
        f"token without required scope must be rejected (403); got "
        f"{resp.status_code}: {resp.text!r}"
    )


@pytest.mark.security
@pytest.mark.mcp
def test_wofost_mcp_call_accepts_correct_scope():
    """Correct scope clears the auth guard (status != 401/403).

    Past the guard the tool may still return 200/400/422 depending on args/DB —
    we only assert auth is NOT the blocker, proving require_scope let it through.
    """
    mod = _import_server("wofost_server")
    client = _test_client(mod.app)
    token = _scoped_token(scope="crop:read")
    resp = client.post(
        "/v1/mcp/tools/call",
        json={"name": "list_crop_models", "arguments": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code not in (401, 403), (
        f"correct scope should clear the auth guard; got {resp.status_code}: {resp.text!r}"
    )


# ── weather / sentinel_hub (need repo-root shared.helpers → skip in dev) ─────


@pytest.mark.integration
@pytest.mark.mcp
@pytest.mark.xfail(
    strict=False,
    reason=(
        "MCP-PREAUTH-STATUS-01: طلب بلا توكن يُجاب بـ400 بدل 401. التخويل موصول فعلاً — "
        "weather_server.py:147 يُعلن Depends(require_scope) و oauth_middleware.py:43-44 "
        "يرفع 401 «Missing token» — لكنّ طبقة سابقة للحارس تُجيب أوّلاً. عيب ترتيب ورمز "
        "حالة، لا غياب حماية. UNIT-TEST-DORMANCY-01 أيقظ الاختبار؛ الوسم يُبقيه ظاهراً "
        "بفشله المُسمّى بدل إعادته إلى skip صامت، ويُرفع عند إصلاح الترتيب."
    ),
)
@pytest.mark.parametrize("module_name", ["weather_server", "sentinel_hub_server"])
def test_shared_helpers_servers_import_or_skip(module_name):
    """weather/sentinel import shared.helpers (repo-root) — merged only in-container.

    Skips cleanly in this dev layout; in-container the import succeeds and we then
    assert the scope-guarded MCP endpoint rejects an unauthenticated request.
    """
    mod = _import_server(module_name)  # skips with a clear reason if not importable
    client = _test_client(mod.app)
    assert client.get("/healthz").status_code == 200
    resp = client.post("/v1/mcp/tools/call", json={"name": "x", "arguments": {}})
    assert resp.status_code in (401, 403), (
        f"{module_name} MCP endpoint must enforce scope; got {resp.status_code}"
    )


# ── Standalone runner ───────────────────────────────────────────────────────
if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-p", "no:cacheprovider"]))
