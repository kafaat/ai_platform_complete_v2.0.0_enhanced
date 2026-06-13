"""Stage F — تقدير الإنتاجيّة يُغذَّى آمناً من الحالة القانونيّة الموحّدة.

يثبّت أنّ POST /api/v1/fields/{field_id}/yield-estimate يمرّ عبر field_state:
يستدعي recompute_field_state ضمن tenant_connection ويُرفِق كتلة field_state +
علامة requires_review بالاستجابة — تغذية آمنة (مرجعيّة/ثقة فقط، لا تغيير رقم
التقدير)، وأنّ النقطة مُسجَّلة (POST). فحص تعاقُد على المصدر + تسجيل، متّسق مع
اختبار التوصيات/التنبيهات.
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


def test_yield_estimate_feeds_from_canonical_state():
    body = _func_src("estimate_field_yield")
    # تغذية آمنة من الحالة الموحّدة: استدعاء recompute_field_state ضمن tenant_connection.
    assert "tenant_connection(user)" in body, "لا يفتح tenant_connection لجلب الحالة"
    assert "recompute_field_state" in body, "لا استدعاء لـrecompute_field_state"
    # إرفاق المرجعيّة: كتلة field_state + علامة requires_review بالاستجابة.
    assert '"field_state"' in body, "لا يُرفِق كتلة field_state بالاستجابة"
    assert '"requires_review"' in body, "لا يُرفِق علامة requires_review"
    assert 'execution_mode") != "auto"' in body, "requires_review لا يُشتقّ من نمط التنفيذ"
    # رقم التقدير يُحسَب قبل جلب الحالة ولا يُمسّ — استدعاء estimate_yield يسبق
    # استدعاء recompute_field_state (تغذية مرجعيّة لا حسابيّة).
    assert body.index("estimate_yield(features)") < body.index("recompute_field_state"), (
        "حساب التقدير يجب أن يسبق جلب الحالة (لا تغيير رقم التقدير)"
    )


def test_yield_estimate_state_failure_is_failsafe():
    body = _func_src("estimate_field_yield")
    lines = body.splitlines()
    rc_idx = next(
        (i for i, ln in enumerate(lines) if "recompute_field_state" in ln and "import" not in ln),
        None,
    )
    assert rc_idx is not None, "لا استدعاء لـrecompute_field_state"
    rc_indent = len(lines[rc_idx]) - len(lines[rc_idx].lstrip())
    # استدعاء جلب الحالة محروس بـtry (fail-safe: تعذّر الحالة لا يكسر التقدير).
    guarded = any(
        ln.strip() == "try:" and (len(ln) - len(ln.lstrip())) < rc_indent for ln in lines[:rc_idx]
    )
    assert guarded, "جلب الحالة ليس داخل try (لا fail-safe)"
    # صدق: غياب الحالة (None) ⇒ لا تُرفَق كتلة field_state.
    assert "field_state is not None" in body, "لا يحرس إرفاق الحالة بغيابها (صدق)"


def test_yield_estimate_post_route_registered(core_on_path):
    import api.main as m

    methods = {
        meth
        for r in m.app.routes
        if getattr(r, "path", None) == "/api/v1/fields/{field_id}/yield-estimate"
        for meth in (getattr(r, "methods", set()) or set())
    }
    assert "POST" in methods, "نقطة POST /api/v1/fields/{field_id}/yield-estimate غير مُسجَّلة"
