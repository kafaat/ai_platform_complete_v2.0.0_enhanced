"""اعتماد نتيجة التربة يُغذّي الحالة القانونيّة الموحّدة (FIELD_STATE_CHANGED).

سدّ فجوة كشفها تدقيق سلسلة الأحداث: نتيجة تربة معتمَدة تُدخِل EC جديداً (تقرؤه
gather_field_freshness) ⇒ قد تتبدّل الملوحة فالحالة. كان المسار القديم نشرَ
soil_lab_tests في update_soil_lab_test؛ وبقرار المالك (W1-03، 2026-11-16) صار
soil_lab_results المخزنَ القانونيّ الوحيد والمسارُ القديم مُجمَّداً (410). يثبّت هذا
الملفّ أنّ انتقال عيّنة المختبر (approved/rejected/cancelled) يُعيد حساب الحالة ويُصدِر
field.state_changed **داخل حارس تبدّل الحالة** (لا عند كلّ نداء)، وأنّ المسار القديم لا
يكتب. فحص تعاقُد على المصدر (بلا قاعدة)، نمط _func_src نفسه.
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
ROUTERS = os.path.join(CORE, "api", "routers")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


def _func_src(name: str) -> str:
    # المعالِج قد يكون في main.py أو في وحدة routers بعد تفكيك monolith (P0).
    # نبحث في main.py أوّلاً ثمّ في كلّ ملفّات routers — يبقى الفحص صحيحاً أينما استقرّ.
    sources = [MAIN]
    if os.path.isdir(ROUTERS):
        sources += [
            os.path.join(ROUTERS, f) for f in sorted(os.listdir(ROUTERS)) if f.endswith(".py")
        ]
    needle = f"async def {name}("
    for path in sources:
        with open(path, encoding="utf-8") as f:
            src = f.read()
        start = src.find(needle)
        if start == -1:
            continue
        nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
        end = (start + 1 + nxt.start()) if nxt else len(src)
        return src[start:end]
    raise AssertionError(f"لم يُعثر على المعالِج `{name}` في main.py ولا في routers/")


def test_lab_transition_routes_through_canonical_state():
    helper = _func_src("_refresh_field_state")
    assert "recompute_field_state" in helper, "لا يُعيد حساب الحالة القانونيّة"
    assert "FIELD_STATE_CHANGED" in helper, "لا يُصدِر حدث تبدّل الحالة"
    assert 'if fs["changed"]' in helper, "يجب أن يُصدِر الحدث فقط حين تتبدّل الحالة"

    body = _func_src("transition_lab_sample")
    lines = body.splitlines()
    rc_idx = next((i for i, ln in enumerate(lines) if "await _refresh_field_state(" in ln), None)
    assert rc_idx is not None, "انتقال العيّنة لا يستدعي _refresh_field_state"
    rc_indent = len(lines[rc_idx]) - len(lines[rc_idx].lstrip())
    guard = lines[rc_idx - 1]
    assert "is_soil" in guard and '"approved"' in guard, (
        "إعادة الحساب يجب أن تقع خلف حارس عيّنة تربة + انتقال اعتماد/سحب"
    )
    assert len(guard) - len(guard.lstrip()) < rc_indent, "الاستدعاء ليس داخل الحارس"
    changed_guard = any(
        ln.strip() == "else:" and (len(ln) - len(ln.lstrip())) < rc_indent - 4
        for ln in lines[:rc_idx]
    )
    assert changed_guard, "إعادة الحساب يجب أن تقع في فرع تبدّل الحالة فقط"
    assert 'f"soil_lab.{payload.target_status}"' in body, "المُحفِّز يجب أن يُسمّي الانتقال"


def test_legacy_soil_lab_update_is_frozen():
    body = _func_src("update_soil_lab_test")
    assert "status_code=410" in body, "المسار القديم يجب أن يُجيب 410 Gone (W1-03)"
    assert "soil_lab_tests" not in body.split('"""')[-1], "المسار القديم لا يلمس الجدول"
    assert "UPDATE" not in body, "المسار القديم لا يكتب"


def test_soil_lab_patch_route_registered(core_on_path):
    import api.main as m

    from conftest import registered_paths

    assert "/api/v1/fields/{field_id}/soil-lab-tests/{test_id}" in registered_paths(m.app), (
        "نقطة تحديث فحص التربة غير مُسجَّلة"
    )
