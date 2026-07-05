#!/usr/bin/env python3
"""يولّد مصفوفة تفويض مسارات sahool-platform من شجرة تبعيّات FastAPI الفعليّة.

يُخرِج docs/api/ROUTE_AUTH_MATRIX.md + يحدّث allowlist القراءات العامّة. يحلّ
التفويض على مستوى المسار/الراوتر/التطبيق (لا مسحاً نصّيّاً). البند #4 من تدقيق 2026-07-05.

الاستعمال: PYTHONPATH=services/sahool-platform:. python3 scripts/ci/gen_route_auth_matrix.py
"""

from __future__ import annotations

_AUTH_FNS = {"get_current_user", "_require_service_token", "require_permission", "require_role"}


def _walk(dep, acc):
    call = getattr(dep, "call", None)
    if call is not None and getattr(call, "__name__", "") in _AUTH_FNS:
        acc.add(call.__name__)
    for sub in getattr(dep, "dependencies", []):
        _walk(sub, acc)


def collect_rows(app):
    rows = []
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if not (path.startswith("/api/v1") or path.startswith("/auth")):
            continue
        dep = getattr(route, "dependant", None)
        acc: set[str] = set()
        if dep is not None:
            _walk(dep, acc)
        for meth in sorted(methods & {"GET", "POST", "PUT", "PATCH", "DELETE"}):
            level = (
                "user-auth"
                if "get_current_user" in acc
                else "service-token"
                if "_require_service_token" in acc
                else "PUBLIC"
            )
            rows.append((meth, path, level))
    return rows


if __name__ == "__main__":
    import api.main as m

    rows = collect_rows(m.app)
    mut = [r for r in rows if r[0] != "GET"]
    pub = sorted(r[1] for r in rows if r[0] == "GET" and r[2] == "PUBLIC")
    print(f"mutating={len(mut)} reads={len(rows) - len(mut)} public_reads={len(pub)}")
    unprotected = [
        f"{r[0]} {r[1]}"
        for r in mut
        if r[2] == "PUBLIC" and r[1] not in ("/api/v1/auth/login", "/api/v1/auth/signup")
    ]
    print("unprotected mutating:", unprotected or "none")
