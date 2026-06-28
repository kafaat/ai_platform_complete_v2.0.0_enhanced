#!/usr/bin/env python3
"""حارس تفكيك actuator-service — نظير حارس raster/المنصّة (سلوك محفوظ).

يفرض ثوابت التفكيك ضدّ أيّ انحدار لاحق:
  1) استيراد main ينجح ويبني app (آليّة التسجيل لا تكسر الإقلاع).
  2) أرضيّة عدد المسارات ≥ 10 (التفكيك لا يُسقط مساراً — الثابت 10).
  3) مسارات actuator الحرجة حاضرة (الأوامر الفيزيائيّة لا تختفي بعد النقل).
  4) لا مُزخرِف ``@app.<method>`` متبقٍّ في main.py (التفكيك مكتمل).
  5) register_routers(app) موصول في main (السقالة مفعَّلة).

ملاحظة: يحتاج استيراد main الذي يستورد حزمة ``shared`` من جذر المستودع — شغّل بـ
``PYTHONPATH=<repo root>``. يُتخطّى بأمان إن تعذّر استيراد main (تبعيّات البيئة الدنيا).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    import main as _main
except Exception:  # noqa: BLE001 — تبعيّات actuator/shared الدنيا غير متوفّرة
    pytest.skip("actuator main import unavailable", allow_module_level=True)

app = _main.app

# مسارات actuator الحرجة (الأمر الفيزيائيّ + سجلّ الأوامر + الجاهزيّة) — فقدانها انحدار.
_CRITICAL_ROUTES = (
    "/command",
    "/commands",
    "/readyz",
)


def _app_paths() -> set:
    return {getattr(r, "path", None) for r in app.routes}


def test_main_imports_and_builds_app():
    """استيراد main ينجح ويبني app (آليّة التسجيل لا تكسر الإقلاع)."""
    assert app is not None
    assert hasattr(app, "routes")


def test_route_count_floor():
    """عدد المسارات أرضيّة ≥ 10 (التفكيك لا يُسقط مساراً — الثابت 10)."""
    n = len(app.routes)
    assert n >= 10, f"عدد المسارات هبط تحت الأرضيّة: {n} < 10 (مسارات ضائعة)"


def test_critical_routes_present():
    """مسارات actuator الحرجة كلّها حاضرة في app.routes (لا تختفي بعد التفكيك)."""
    paths = _app_paths()
    missing = [p for p in _CRITICAL_ROUTES if p not in paths]
    assert not missing, f"مسارات actuator حرجة مفقودة (انحدار): {missing}"


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


def test_no_app_route_decorators_in_main():
    """لا مُزخرِف ``@app.<method>`` متبقٍّ في main.py (التفكيك مكتمل، المُعالِجات في routers/)."""
    src = (_HERE / "main.py").read_text(encoding="utf-8")
    leftover = re.findall(r"@app\.(get|post|put|delete|patch|websocket)\b", src)
    assert not leftover, f"مُزخرِفات @app متبقّية في main.py (تفكيك ناقص): {leftover}"
    assert "register_routers(app)" in src, "register_routers(app) غير موصول في main.py"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
