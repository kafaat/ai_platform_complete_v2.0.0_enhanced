"""نشر نتيجة التربة يُغذّي الحالة القانونيّة الموحّدة (FIELD_STATE_CHANGED).

سدّ فجوة كشفها تدقيق سلسلة الأحداث: نشر فحص تربة يُدخِل EC جديداً (تقرؤه
gather_field_freshness من soil_lab_tests المنشورة) ⇒ قد تتبدّل الملوحة فالحالة.
يثبّت أنّ update_soil_lab_test عند النشر يُعيد حساب الحالة ويُصدِر field.state_changed
بمُحفِّز soil_lab.published — **داخل حارس النشر** (لا عند كلّ تحديث)، متّسق مع نمط
create_alert/create_season. فحص تعاقُد على المصدر (بلا قاعدة)، نمط _func_src نفسه.
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


def test_publish_routes_through_canonical_state():
    body = _func_src("update_soil_lab_test")
    assert "FIELD_STATE_CHANGED" in body, "لا يُصدِر حدث تبدّل الحالة عند النشر"
    assert "soil_lab.published" in body, "لا يوسم المُحفِّز بـsoil_lab.published"

    # استدعاء recompute_field_state يجب أن يقع داخل حارس النشر (إزاحة أكبر من سطر
    # `if status_changed and req.status == "published":`) — لا عند كلّ تحديث تربة.
    lines = body.splitlines()
    rc_idx = next(
        (i for i, ln in enumerate(lines) if "recompute_field_state" in ln and "import" not in ln),
        None,
    )
    assert rc_idx is not None, "لا استدعاء لـrecompute_field_state"
    rc_indent = len(lines[rc_idx]) - len(lines[rc_idx].lstrip())
    guarded = any(
        'req.status == "published"' in ln and (len(ln) - len(ln.lstrip())) < rc_indent
        for ln in lines[:rc_idx]
    )
    assert guarded, "recompute_field_state ليس داخل حارس النشر (status == published)"


def test_soil_lab_patch_route_registered(core_on_path):
    import api.main as m

    routes = {
        getattr(r, "path", None)
        for r in m.app.routes
        if "soil-lab-tests/{test_id}" in (getattr(r, "path", "") or "")
    }
    assert "/api/v1/fields/{field_id}/soil-lab-tests/{test_id}" in routes, (
        "نقطة تحديث فحص التربة غير مُسجَّلة"
    )
