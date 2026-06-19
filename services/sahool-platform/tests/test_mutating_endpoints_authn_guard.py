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
_AUTH_FNS = {"get_current_user", "_require_service_token"}

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
