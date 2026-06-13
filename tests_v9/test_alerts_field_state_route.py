"""Stage C2 — التنبيهات تمرّ عبر الحالة القانونيّة الموحّدة (Canonical Field State).

يثبّت أنّ POST /api/v1/alerts (إنشاء تنبيه على حقل) يمرّ عبر field_state: يستدعي
recompute_field_state **داخل حارس req.field_id** ويُصدِر FIELD_STATE_CHANGED، وأنّ
النقطة مُسجَّلة (POST) — فحص تعاقُد على المصدر + تسجيل، متّسق مع اختبار التوصيات.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
MAIN = os.path.join(CORE, "api", "main.py")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


def _func_src(name: str) -> str:
    with open(MAIN, encoding="utf-8") as f:
        src = f.read()
    start = src.index(f"async def {name}(")
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    end = (start + 1 + nxt.start()) if nxt else len(src)
    return src[start:end]


def test_create_alert_routes_through_canonical_state():
    body = _func_src("create_alert")
    assert "FIELD_STATE_CHANGED" in body, "لا يُصدِر حدث تبدّل الحالة"
    assert "alert.created" in body, "لا يوسم المُحفِّز بـalert.created"

    # استدعاء recompute_field_state يجب أن يقع داخل حارس `if req.field_id is not None:`
    # (إزاحة أكبر من سطر حارس سابق) — لا مجرّد وجود السلسلة في مكان ما.
    lines = body.splitlines()
    rc_idx = next(
        (i for i, ln in enumerate(lines) if "recompute_field_state" in ln and "import" not in ln),
        None,
    )
    assert rc_idx is not None, "لا استدعاء لـrecompute_field_state"
    rc_indent = len(lines[rc_idx]) - len(lines[rc_idx].lstrip())
    guarded = any(
        ln.strip() == "if req.field_id is not None:" and (len(ln) - len(ln.lstrip())) < rc_indent
        for ln in lines[:rc_idx]
    )
    assert guarded, "recompute_field_state ليس داخل حارس req.field_id is not None"


def test_alerts_post_route_registered(core_on_path):
    import api.main as m

    methods = {
        meth
        for r in m.app.routes
        if getattr(r, "path", None) == "/api/v1/alerts"
        for meth in (getattr(r, "methods", set()) or set())
    }
    assert "POST" in methods, "نقطة POST /api/v1/alerts غير مُسجَّلة"
