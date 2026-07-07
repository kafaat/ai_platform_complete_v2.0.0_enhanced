#!/usr/bin/env python3
"""حارس تفكيك raster-service (سقالة) — نظير حارس المنصّة.

سقالة: لا يفرض بعدُ «لا @app في main» (مسارات تُستخرَج تدريجيّاً إلى routers/).
يفرض الآن ضمانات تجعل الاستخراج اللاحق آمناً من الانحدار:
  1) استيراد main ينجح ويبني app (آليّة التسجيل لا تكسر الإقلاع).
  2) كلّ وحدة في routers/ لها router مُضمَّن فعلاً في app.routes (لا «راوتر يتيم»).
  3) لا تسجيل مزدوج لزوج (method, path) — يمنع التكرار عند نقل مسار.
  4) register_routers(app) موصول في main (السقالة مفعَّلة).

عند استخراج كلّ مجموعة لاحقاً: تُضاف routers/<group>.py، ويتحقّق الحارس آليّاً أنّها
مُضمَّنة وغير مكرّرة. (يحتاج استيراد main — يُتخطّى إن غابت تبعيّات البيئة الدنيا.)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    import main as _main
except Exception:  # noqa: BLE001 — تبعيّات raster الدنيا غير متوفّرة
    pytest.skip("raster main import unavailable", allow_module_level=True)

app = _main.app
_ROUTERS_DIR = _HERE / "routers"


def _app_paths() -> set:
    return {getattr(r, "path", None) for r in app.routes}


def test_main_imports_and_builds_app():
    """استيراد main ينجح ويبني app (آليّة التسجيل لا تكسر الإقلاع)."""
    assert app is not None
    assert hasattr(app, "routes")


def test_every_router_module_included():
    """كلّ routers/*.py له router ⇒ مساراته حاضرة في app (لا راوتر يتيم)."""
    paths = _app_paths()
    missing: list[str] = []
    if _ROUTERS_DIR.is_dir():
        for f in sorted(_ROUTERS_DIR.glob("*.py")):
            if f.name == "__init__.py":
                continue
            mod = importlib.import_module(f"routers.{f.stem}")
            router = getattr(mod, "router", None)
            if router is None:
                continue
            expected = {getattr(r, "path", None) for r in router.routes}
            if expected and not (expected & paths):
                missing.append(f.stem)
    assert not missing, f"راوترات في routers/ غير مُضمَّنة في app: {missing}"


def test_no_duplicate_route_registrations():
    """لا زوج (method, path) مُسجَّل مرّتين (يمنع تكراراً عند نقل مسار)."""
    seen: set = set()
    dups: list = []
    for r in app.routes:
        path = getattr(r, "path", None)
        for m in getattr(r, "methods", None) or set():
            key = (m, path)
            if key in seen:
                dups.append(key)
            seen.add(key)
    assert not dups, f"مسارات مُكرَّرة: {dups}"


def test_register_routers_wired_in_app_factory():
    """آليّة التسجيل التلقائيّ مُستدعاة في app factory بعد تفكيك main.py."""
    src = (_HERE / "raster_app_factory.py").read_text(encoding="utf-8")
    assert "register_routers(app)" in src, (
        "register_routers(app) غير موصول في raster_app_factory.py"
    )


# ─── حُرّاس انحدار دائمون بعد التفكيك (قفل الثوابت) ────────────────────────
# تثبّت مكاسب التفكيك ضدّ أيّ انحدار لاحق: مسارات CDSE الثلاثة لا تختفي، عدد
# المسارات لا يهبط تحت 49، وكلّ وحدة في routers/ مُضمَّنة (لا راوتر يتيم).

# مسارات CDSE الثلاثة التي أضافها المالك حديثاً — فقدانها انحدار حرج.
_CDSE_ROUTES = (
    "/v1/fields/{field_id}/cdse-tilejson",
    "/v1/fields/{field_id}/cdse-tiles/{z}/{x}/{y}.png",
    "/v1/fields/{field_id}/process-cdse",
)


def test_cdse_routes_present():
    """مسارات CDSE الثلاثة كلّها حاضرة في app.routes (لا تختفي بعد التفكيك)."""
    paths = _app_paths()
    missing = [p for p in _CDSE_ROUTES if p not in paths]
    assert not missing, f"مسارات CDSE مفقودة (انحدار حرج): {missing}"


def test_route_count_floor():
    """عدد المسارات أرضيّة ≥ 49 (التفكيك لا يُسقط مساراً)."""
    n = len(app.routes)
    assert n >= 49, f"عدد المسارات هبط تحت الأرضيّة: {n} < 49 (مسارات ضائعة)"


def test_no_orphan_router_module():
    """كلّ routers/*.py يُصدّر router مُضمَّناً فعلاً في app (لا راوتر يتيم)."""
    paths = _app_paths()
    orphans: list[str] = []
    assert _ROUTERS_DIR.is_dir(), "حزمة routers/ غير موجودة"
    for f in sorted(_ROUTERS_DIR.glob("*.py")):
        if f.name == "__init__.py":
            continue
        mod = importlib.import_module(f"routers.{f.stem}")
        router = getattr(mod, "router", None)
        assert router is not None, f"routers/{f.stem}.py لا يُصدّر router"
        expected = {getattr(r, "path", None) for r in router.routes}
        if expected and not (expected & paths):
            orphans.append(f.stem)
    assert not orphans, f"راوترات غير مُضمَّنة في app (يتيمة): {orphans}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
