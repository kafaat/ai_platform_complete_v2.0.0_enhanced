"""حارس بنيويّ لتفكيك main إلى routers (يحمي مكسب التفكيك من الانحدار).

بعد تفكيك monolith (main.py: ‎11,067 → ~4,300 سطر، 96 router)، صار كلّ نقاط
‏`/api/v1/*` في وحدات `api/routers/`. هذا الحارس يمنع الانحدار الصامت:

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
    """كلّ ملفّ router مُستورَد ومُضمَّن في main — لا router يتيم."""
    src = _main_src()
    missing_import: list[str] = []
    missing_include: list[str] = []
    for name in _router_module_names():
        # استيراد قد يكون سطراً واحداً أو ملفوفاً متعدّد الأسطر (ruff يلفّ الطويل):
        #   from api.routers.<name> import router as <alias>
        #   from api.routers.<name> import (\n    router as <alias>,\n)
        m = re.search(
            rf"from api\.routers\.{re.escape(name)} import "
            rf"\(?[ \t]*(?:#[^\n]*)?\s*router as (\w+)",
            src,
        )
        if not m:
            missing_import.append(name)
            continue
        alias = m.group(1)
        if not re.search(rf"app\.include_router\(\s*{re.escape(alias)}\b", src):
            missing_include.append(name)
    assert missing_import == [], f"ملفّات router غير مُستورَدة في main: {missing_import}"
    assert missing_include == [], (
        f"router مُستورَد لكن غير مُضمَّن (app.include_router): {missing_include}"
    )


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
    for r in app.routes:
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
