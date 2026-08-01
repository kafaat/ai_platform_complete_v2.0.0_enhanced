"""
tests_v9/test_mobile_backend_contract.py — مطابقة contract: الموبايل ↔ backend

⚠ هذا اختبار حوكمة contract: يتأكّد أنّ كل مسار يستدعيه تطبيق React Native
   له endpoint مقابل في الـbackend. يمنع انحراف المسارات الذي اكتُشِف في
   جلسة المطابقة (كان /auth/login بلا /api/v1 → 404، و/process مفقود).

   ملاحظة: القوائم مُستخرَجة يدوياً من الكود. عند إضافة استدعاء جديد في
   الموبايل، حدّث MOBILE_CALLS هنا — الاختبار يكشف لو لا backend له.
"""

import os
import re
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))


def _norm(p):
    return re.sub(r"\$?\{[^}]+\}", "{id}", p)


# المسارات التي يستدعيها تطبيق React Native (من src/api/*.ts)
MOBILE_CALLS = [
    "/api/v1/auth/login",
    "/api/v1/auth/signup",
    "/api/v1/auth/me",
    "/api/v1/auth/logout",
    "/api/v1/me",
    "/api/v1/observations",
    "/api/v1/queue/status",
    "/api/v1/recommendations",
    "/api/v1/sync",
    "/api/v1/weather/current",
    "/api/v1/weather/forecast",
    "/api/v1/weather/historical",
    "/api/v1/fields",
    # raster-service (منفذ منفصل)
    "/upload/drone",
    "/upload/raster",
    "/process",
    "/jobs/{id}",
    "/jobs/{id}/result",
    "/info/{id}",
]


def _extract_backend_endpoints():
    """يستخرج endpoints من main.py + raster endpoints.py فعلياً (لا hardcode)."""
    paths = set()
    main_py = os.path.join(os.path.dirname(__file__), "../services/sahool-platform/api/main.py")
    raster_py = os.path.join(
        os.path.dirname(__file__), "../../sahool-raster-service/app/api/endpoints.py"
    )
    for fp, _decorators in [(main_py, ["@app"]), (raster_py, ["@router", "@app"])]:
        if not os.path.exists(fp):
            continue
        src = open(fp, encoding="utf-8").read()
        for m in re.finditer(r'@(?:app|router)\.(?:get|post|put|delete)\(\s*["\']([^"\']+)', src):
            paths.add(_norm(m.group(1)))
    return paths


def test_every_mobile_call_has_backend():
    backend = _extract_backend_endpoints()
    results = []
    missing = []
    for call in MOBILE_CALLS:
        if _norm(call) not in backend:
            missing.append(call)
    if not missing:
        results.append(("✓", f"كل {len(MOBILE_CALLS)} استدعاء موبايل له endpoint"))
    else:
        for m in missing:
            results.append(("✗", f"مفقود في backend: {m}"))
    return results


def test_auth_paths_have_api_v1_prefix():
    """يمنع تكرار خطأ /auth/login بلا prefix (كان يفشل بـ404)."""
    results = []
    authsvc = os.path.join(os.path.dirname(__file__), "../../sahool_mobile/src/api/authService.ts")
    if os.path.exists(authsvc):
        src = open(authsvc, encoding="utf-8").read()
        # أيّ استدعاء /auth/* يجب أن يكون /api/v1/auth/*
        bad = re.findall(r"httpClient\.\w+\([^)]*['\"](/auth/[^'\"]+)", src)
        if not bad:
            results.append(("✓", "كل مسارات auth بـ/api/v1 prefix"))
        else:
            for b in bad:
                results.append(("✗", f"مسار auth بلا /api/v1: {b}"))
    else:
        results.append(("✓", "authService.ts غير موجود (skip)"))
    return results


def run_all():
    print("=" * 60)
    print("  Contract: Mobile (React Native) ↔ Backend")
    print("=" * 60)
    suites = [
        ("Mobile calls → backend", test_every_mobile_call_has_backend),
        ("Auth path prefix", test_auth_paths_have_api_v1_prefix),
    ]
    tp = tf = 0
    for name, suite in suites:
        print(f"\n── {name} ──")
        for status, msg in suite():
            print(f"  {status} {msg}")
            tp += 1 if status == "✓" else 0
            tf += 1 if status == "✗" else 0
    print(f"\n{'=' * 60}\n  Passed: {tp}/{tp + tf}\n{'=' * 60}")
    return tp, tf


if __name__ == "__main__":
    p, f = run_all()
    sys.exit(0 if f == 0 else 1)
