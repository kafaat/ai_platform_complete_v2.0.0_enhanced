"""حارس بنيويّ لتفكيك main إلى routers (يحمي مكسب التفكيك من الانحدار).

بعد تفكيك monolith (main.py: 11,067 → ~4,300 سطر، 96 router)، صار كلّ نقاط
`/api/v1/*` في وحدات `api/routers/`. هذا الحارس يمنع الانحدار الصامت:

  ١) لا تُعرَّف أيّ نقطة `/api/v1/*` بـ`@app.<method>` في main.py — يجب أن تذهب
     إلى router (تبقى في main فقط نقاط البنية: /healthz، /readyz، الجذر،
     /internal/…).
  ٢) كلّ ملفّ router في `api/routers/` (عدا __init__) مُستورَد ومُضمَّن عبر
     `app.include_router` في main — لا ملفّ router يتيم.
  ٣) لا تكرار لزوج (مسار، طريقة) في مخطّط المسارات الحيّ.

فحص تعاقُد على المصدر + على `app.routes` — لا قاعدة بيانات.
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

HERE = os.path.dirname(__file__)
API = os.path.join(HERE, "..", "api")
MAIN = os.path.join(API, "main.py")
ROUTERS_DIR = os.path.join(API, "routers")

# نقاط البنية المسموح بقاؤها في main (ليست نطاق `/api/v1`).
_INFRA_PREFIXES = ("/healthz", "/readyz", "/internal", "/metrics")


def _main_src() -> str:
    with open(MAIN, encoding="utf-8") as f:
        return f.read()


def _router_module_names() -> list[str]:
    return sorted(
        f[:-3] for f in os.listdir(ROUTERS_DIR) if f.endswith(".py") and f != "__init__.py"
    )


def _effective_app_routes(app) -> list:
    """Flatten FastAPI 0.136 lazy ``_IncludedRouter`` wrappers."""
    out = []
    for route in app.routes:
        original = getattr(route, "original_router", None)
        out.extend(getattr(original, "routes", []) if original is not None else [route])
    return out


def test_no_api_v1_endpoints_remain_in_main():
    """لا نقطة `/api/v1/*` مُعرَّفة مباشرةً بـ@app في main (يجب أن تكون في router)."""
    src = _main_src()
    offenders = re.findall(r'@app\.(?:get|post|put|patch|delete)\(\s*["\'](/api/v1/[^"\']*)', src)
    assert offenders == [], (
        f"نقاط `/api/v1` يجب أن تُعرَّف في api/routers/ لا في main.py؛ عادت هذه إلى main: {offenders}"
    )


def test_residual_app_endpoints_are_infrastructure_only():
    """ما يبقى من @app في main حصراً نقاط بنية (لا نطاق عمل)."""
    src = _main_src()
    paths = re.findall(r'@app\.(?:get|post|put|patch|delete)\(\s*["\']([^"\']+)', src)
    non_infra = [p for p in paths if not p.startswith(_INFRA_PREFIXES)]
    assert non_infra == [], f"نقاط @app غير-بنيويّة بقيت في main: {non_infra}"


def test_every_router_module_is_included_in_main():
    """كلّ ملفّ router مُضمَّن في التطبيق فعليّاً — لا router يتيم.

    بعد التحوّل إلى التسجيل التلقائيّ (api/main.py يضمّن كلّ راوتر في api/routers/
    عبر حلقة pkgutil)، صار التحقّق عبر `app.routes` (وقت التشغيل) أمتنَ من مطابقة
    نصّ main.py: نؤكّد أنّ مسارات كلّ وحدة راوتر حاضرة في مخطّط التطبيق المُجمَّع."""
    import sys

    core = os.path.join(HERE, "..")
    if core not in sys.path:
        sys.path.insert(0, core)
    pytest.importorskip("fastapi")
    import importlib

    from api.main import app

    app_paths = {getattr(r, "path", None) for r in _effective_app_routes(app)}

    missing: list[str] = []
    for name in _router_module_names():
        mod = importlib.import_module(f"api.routers.{name}")
        router = getattr(mod, "router", None)
        if router is None:
            # وحدة لا تُصدّر router (نادر) — لا تُسجَّل ولا تُعدّ يتيمة.
            continue
        prefix = getattr(router, "prefix", "") or ""
        # في إصدار FastAPI/Starlette الحاليّ يتضمّن ``rt.path`` بادئة الراوتر مسبقاً
        # (لراوتر بـ``prefix=...``)، فإضافة البادئة ثانيةً تُضاعفها وتُسقط المطابقة
        # خطأً (مثل gis_cloud_native، الراوتر الوحيد ذو البادئة). نتفادى الازدواج:
        # نُبقي المسار كما هو إن كان يبدأ بالبادئة، وإلّا نُضيفها.
        expected = set()
        for rt in router.routes:
            if not hasattr(rt, "path"):
                continue
            rp = getattr(rt, "path", "")
            expected.add(rp if (not prefix or rp.startswith(prefix)) else prefix + rp)
        if expected and not (expected & app_paths):
            missing.append(name)
    assert missing == [], f"router غير مُضمَّن في التطبيق (app.routes): {missing}"


def test_no_duplicate_route_registrations():
    """لا تكرار لزوج (مسار، طريقة) في مخطّط المسارات الحيّ (تضمين مزدوج)."""
    import sys

    core = os.path.join(HERE, "..")
    if core not in sys.path:
        sys.path.insert(0, core)
    pytest.importorskip("fastapi")
    from api.main import app

    seen: set[tuple[str, str]] = set()
    dups: list[tuple[str, str]] = []
    for r in _effective_app_routes(app):
        methods = getattr(r, "methods", None)
        path = getattr(r, "path", None)
        if not methods or path is None:
            continue
        for method in methods:
            key = (path, method)
            if key in seen:
                dups.append(key)
            seen.add(key)
    assert dups == [], f"مسارات مُسجَّلة مرّتين (تضمين router مزدوج؟): {dups}"
