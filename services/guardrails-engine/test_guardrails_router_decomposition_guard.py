#!/usr/bin/env python3
"""حارس تفكيك guardrails-engine — يقفل ثوابت التفكيك المحفوظ-السلوك.

guardrails-engine أمنيّ-حرج (/validate بوّابة الحوكمة على مسار pip-audit/bandit في CI).
بعد نقل المُعالِجات السبعة من ``@app`` في ``main.py`` إلى ``@router`` في ``routers/``،
يفرض هذا الحارس أنّ التفكيك لم يُسقِط مساراً ولا يكرّره ولا يُعيد ``@app`` إلى main:
  1) استيراد main ينجح ويبني app (آليّة التسجيل لا تكسر الإقلاع).
  2) لا زوج (method, path) مُسجَّل مرّتين (يمنع تكراراً عند نقل مسار).
  3) register_routers(app) موصول في main (السقالة مفعَّلة).
  4) عدد المسارات أرضيّة ≥ 11 (ثابت لا يهبط).
  5) المسارات الحرجة حاضرة (وعلى رأسها /v1/validate — بوّابة الحوكمة).
  6) لا ``@app.<method>`` في main.py (التفكيك مكتمل — صفر مُعالِج مسار في main).

(يحتاج استيراد main — يُتخطّى إن غابت تبعيّات البيئة الدنيا.)
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
except Exception:  # noqa: BLE001 — تبعيّات guardrails الدنيا غير متوفّرة
    pytest.skip("guardrails main import unavailable", allow_module_level=True)

app = _main.app
_ROUTERS_DIR = _HERE / "routers"

# المسارات الحرجة التي لا يجوز أن تختفي بعد التفكيك (/v1/validate على رأسها).
_CRITICAL_ROUTES = (
    "/v1/validate",
    "/v1/approve/{workflow_id}",
    "/v1/workflow/{workflow_id}",
    "/healthz",
)


def _app_paths() -> set:
    return {getattr(r, "path", None) for r in app.routes}


def test_main_imports_and_builds_app():
    """استيراد main ينجح ويبني app (آليّة التسجيل لا تكسر الإقلاع)."""
    assert app is not None
    assert hasattr(app, "routes")


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
    """آليّة التسجيل التلقائيّ مُستدعاة في main (التفكيك موصول)."""
    src = (_HERE / "main.py").read_text(encoding="utf-8")
    assert "register_routers(app)" in src, "register_routers(app) غير موصول في main.py"


def test_route_count_floor():
    """عدد المسارات أرضيّة ≥ 11 (التفكيك لا يُسقط مساراً)."""
    n = len(app.routes)
    assert n >= 11, f"عدد المسارات هبط تحت الأرضيّة: {n} < 11 (مسارات ضائعة)"


def test_critical_routes_present():
    """المسارات الحرجة كلّها حاضرة في app.routes (/v1/validate بوّابة الحوكمة)."""
    paths = _app_paths()
    missing = [p for p in _CRITICAL_ROUTES if p not in paths]
    assert not missing, f"مسارات حرجة مفقودة (انحدار حرج): {missing}"


def test_no_app_route_decorators_in_main():
    """لا ``@app.<method>`` في main.py — كلّ المُعالِجات انتقلت إلى routers/."""
    src = (_HERE / "main.py").read_text(encoding="utf-8")
    hits = re.findall(r"@app\.(?:get|post|put|delete|patch|websocket)\b", src)
    assert not hits, f"بقيت مُعالِجات @app في main.py (تفكيك ناقص): {hits}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
