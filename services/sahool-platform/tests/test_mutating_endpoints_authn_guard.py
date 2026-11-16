"""حارس بنيويّ (H1): كلّ نقطة مُغيِّرة (POST/PUT/PATCH/DELETE) يجب أن تتطلّب مصادقة.

fail-closed بنيويّ: أيّ نقطة كتابة جديدة بلا `Depends(get_current_user)` (مباشرةً أو
عبر require_permission/require_role) ولا `_require_service_token` تُفشِل هذا الاختبار —
يمنع انحدار «نقطة مكشوفة منسيّة». الاستثناءات العامّة (دخول/تسجيل…) صريحة في allowlist.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import api.main as m  # noqa: E402

# دوالّ المصادقة المقبولة في شجرة التبعيّات (get_current_user يظهر أيضاً ضمن
# require_permission/require_role لأنّهما يعتمدانه؛ والخدمة-لخدمة عبر service token).
_AUTH_FNS = {"get_current_user", "_require_service_token", "edge_sync_actor"}
# edge_sync_actor (W0-07, api/routers/edge.py) is dual-mode: it calls _require_service_token plus
# a tenant assertion, or get_current_user, itself rather than declaring either as a dependency.
# Its name is accepted only because test_dual_mode_auth_functions_fail_closed proves it refuses.

# نقاط مُغيِّرة عامّة صراحةً (لا تتطلّب مصادقة بحكم وظيفتها) — تُراجَع بوعي.
# الدخول/التسجيل عامّان بالضرورة (لا يمكن المصادقة قبلهما).
_PUBLIC_ALLOWLIST: set[tuple[str, str]] = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/signup"),
}


def _auth_in_tree(dep) -> bool:
    call = getattr(dep, "call", None)
    if call is not None and getattr(call, "__name__", "") in _AUTH_FNS:
        return True
    return any(_auth_in_tree(sub) for sub in getattr(dep, "dependencies", []))


def _mutating_routes():
    for route in m.app.routes:
        methods = getattr(route, "methods", None) or set()
        for meth in methods & {"POST", "PUT", "PATCH", "DELETE"}:
            yield meth, getattr(route, "path", ""), route


def test_all_mutating_endpoints_require_auth():
    unprotected = []
    for meth, path, route in _mutating_routes():
        if (meth, path) in _PUBLIC_ALLOWLIST:
            continue
        dependant = getattr(route, "dependant", None)
        if dependant is None or not _auth_in_tree(dependant):
            unprotected.append(f"{meth} {path}")
    assert not unprotected, "نقاط مُغيِّرة بلا مصادقة (fail-open):\n  " + "\n  ".join(
        sorted(unprotected)
    )


def test_dual_mode_auth_functions_fail_closed(monkeypatch):
    """Every name in _AUTH_FNS beyond the two primitives must refuse an anonymous caller."""
    from api.routers.edge import edge_sync_actor
    from fastapi import HTTPException
    from starlette.requests import Request

    def request(headers):
        raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        return Request({"type": "http", "method": "POST", "path": "/v1/edge/sync", "headers": raw})

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "unit-service-token")
    with pytest.raises(HTTPException) as anonymous:
        edge_sync_actor(request({}), authorization=None)
    assert anonymous.value.status_code == 401, anonymous.value.detail
    with pytest.raises(HTTPException) as unsigned:
        edge_sync_actor(request({"X-Service-Name": "edge-inference"}), authorization=None)
    assert unsigned.value.status_code == 403, unsigned.value.detail
    with pytest.raises(HTTPException) as token_only:
        edge_sync_actor(
            request({"X-Service-Name": "edge-inference", "X-Agent-Token": "unit-service-token"}),
            authorization=None,
        )
    assert token_only.value.status_code in {401, 403, 503}, token_only.value.detail
