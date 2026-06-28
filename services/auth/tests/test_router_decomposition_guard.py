#!/usr/bin/env python3
"""حارس تفكيك auth-service (خدمة مصادقة حسّاسة أمنيّاً) — نظير حارس المنصّة/raster.

تفكيك ``services/auth/main.py`` نقل مُعالِجات المسارات الـ٢٧ من ``@app.<method>`` في
``main.py`` إلى ``@router.<method>`` في وحدات ``routers/`` (سلوك محفوظ، عدد المسارات
ثابت). هذا الحارس يمنع أيّ انحدار لاحق:

  1) استيراد main ينجح ويبني app (آليّة التسجيل/التسطيح لا تكسر الإقلاع).
  2) عدد المسارات لا يهبط تحت الأرضيّة N (لا مسار يضيع عند نقل/إعادة تنظيم).
  3) كلّ وحدة في routers/ تُصدّر router مُضمَّناً فعلاً في app (لا «راوتر يتيم»).
  4) لا تسجيل مزدوج لزوج (method, path) — يمنع التكرار عند نقل مسار.
  5) main.py خلا من مُزخرِفات المسارات ``@app.(get|post|...)`` (التفكيك مكتمل) —
     يُسمح فقط بـ@app.middleware/@app.on_event (ليست مسارات).
  6) register_routers(app) موصول في main (السقالة مفعَّلة).

يتطلّب استيراد main — يُتخطّى بأمان إن غابت تبعيّات البيئة الدنيا (fastapi/jose…).
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_HERE = Path(__file__).resolve().parent
_AUTH_DIR = _HERE.parent
if str(_AUTH_DIR) not in sys.path:
    sys.path.insert(0, str(_AUTH_DIR))

# أرضيّة عدد المسارات = الخطّ الأساس وقت التفكيك (٤ مسارات FastAPI افتراضيّة +
# ٢٧ مسار APIRoute للمُعالِجات). أيّ هبوط ⇒ مسار ضائع (انحدار حرج).
_ROUTE_FLOOR = 31

try:
    import main as _main
except Exception as e:  # noqa: BLE001 — تبعيّات auth الدنيا غير متوفّرة في بيئة خفيفة
    pytest.skip(f"auth main import unavailable: {e}", allow_module_level=True)

app = _main.app
_ROUTERS_DIR = _AUTH_DIR / "routers"


def _app_paths() -> set:
    return {getattr(r, "path", None) for r in app.routes}


def test_main_imports_and_builds_app():
    """استيراد main ينجح ويبني app (آليّة التسجيل/التسطيح لا تكسر الإقلاع)."""
    assert app is not None
    assert hasattr(app, "routes")


def test_route_count_floor():
    """عدد المسارات ≥ الأرضيّة (التفكيك لا يُسقط مساراً)."""
    n = len(app.routes)
    assert n >= _ROUTE_FLOOR, f"عدد المسارات هبط تحت الأرضيّة: {n} < {_ROUTE_FLOOR} (مسار ضائع)"


def test_no_orphan_router_module():
    """كلّ routers/*.py يُصدّر router مُضمَّناً فعلاً في app (لا راوتر يتيم)."""
    paths = _app_paths()
    orphans: list[str] = []
    assert _ROUTERS_DIR.is_dir(), "حزمة routers/ غير موجودة"
    found_any = False
    for f in sorted(_ROUTERS_DIR.glob("*.py")):
        if f.name == "__init__.py":
            continue
        found_any = True
        mod = importlib.import_module(f"routers.{f.stem}")
        router = getattr(mod, "router", None)
        assert router is not None, f"routers/{f.stem}.py لا يُصدّر router"
        expected = {getattr(r, "path", None) for r in router.routes}
        if expected and not (expected & paths):
            orphans.append(f.stem)
    assert found_any, "حزمة routers/ فارغة — لم تُستخرَج أيّ وحدة"
    assert not orphans, f"راوترات في routers/ غير مُضمَّنة في app (يتيمة): {orphans}"


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


def test_main_has_no_app_route_decorators():
    """التفكيك مكتمل: لا @app.(get|post|put|patch|delete) في main.py (المسارات في routers/).

    يُسمح بـ@app.middleware و@app.on_event فقط (ليست مسارات HTTP).
    """
    src = (_AUTH_DIR / "main.py").read_text(encoding="utf-8")
    offenders = re.findall(r"@app\.(get|post|put|patch|delete|head|options)\b", src)
    assert not offenders, f"مسارات ما تزال في main.py (لم تُفكَّك): @app.{offenders}"


def test_register_routers_wired_in_main():
    """آليّة التسجيل التلقائيّ مُستدعاة في main (السقالة موصولة)."""
    src = (_AUTH_DIR / "main.py").read_text(encoding="utf-8")
    assert "register_routers(app)" in src, "register_routers(app) غير موصول في main.py"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
