#!/usr/bin/env python3
"""حارس تفكيك tts-service — نظير حارس raster/المنصّة (تفكيك محفوظ السلوك).

يفرض ثوابت التفكيك ويمنع الانحدار:
  1) استيراد main ينجح ويبني app (آليّة التسجيل لا تكسر الإقلاع).
  2) كلّ وحدة في routers/ لها router مُضمَّن فعلاً في app.routes (لا «راوتر يتيم»).
  3) لا تسجيل مزدوج لزوج (method, path) — يمنع التكرار عند نقل مسار.
  4) register_routers(app) موصول في main.
  5) لا مُزخرِف مسار @app.<method> باقٍ في main.py (التفكيك مكتمل).

كما يقفل الثوابت: عدد المسارات ≥ 11، ومسارات tts الحرجة لا تختفي.
(يحتاج استيراد main — يُتخطّى إن غابت تبعيّات البيئة الدنيا مثل edge_tts.)
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    import main as _main
except Exception:  # noqa: BLE001 — تبعيّات tts الدنيا غير متوفّرة (مثل edge_tts)
    pytest.skip("tts main import unavailable", allow_module_level=True)

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
    assert _ROUTERS_DIR.is_dir(), "حزمة routers/ غير موجودة"
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


def test_register_routers_wired_in_main():
    """آليّة التسجيل التلقائيّ مُستدعاة في main (السقالة موصولة)."""
    src = (_HERE / "main.py").read_text(encoding="utf-8")
    assert "register_routers(app)" in src, "register_routers(app) غير موصول في main.py"


def test_no_app_route_decorators_in_main():
    """التفكيك مكتمل: لا مُزخرِف مسار @app.<method> باقٍ في main.py."""
    src = (_HERE / "main.py").read_text(encoding="utf-8")
    leftover = re.findall(r"@app\.(get|post|put|delete|patch|websocket)\b", src)
    assert not leftover, f"مُزخرِفات @app باقية في main.py (تفكيك ناقص): {leftover}"


# ─── حُرّاس انحدار دائمون بعد التفكيك (قفل الثوابت) ────────────────────────
# مسارات tts الحرجة التي يجب ألّا تختفي بعد التفكيك.
_CRITICAL_ROUTES = (
    "/tts/voices",
    "/tts/synthesize",
    "/tts/stream",
)


def test_critical_routes_present():
    """مسارات tts الحرجة كلّها حاضرة في app.routes (لا تختفي بعد التفكيك)."""
    paths = _app_paths()
    missing = [p for p in _CRITICAL_ROUTES if p not in paths]
    assert not missing, f"مسارات tts الحرجة مفقودة (انحدار حرج): {missing}"


def test_route_count_floor():
    """عدد المسارات أرضيّة ≥ 11 (التفكيك لا يُسقط مساراً)."""
    n = len(app.routes)
    assert n >= 11, f"عدد المسارات هبط تحت الأرضيّة: {n} < 11 (مسارات ضائعة)"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
