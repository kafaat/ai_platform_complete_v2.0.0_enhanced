"""لوحة المؤشّرات (/api/v1/indicators/dashboard) — تحقّق عقد الشكل + geometry.

الخلفيّة: تطبيق الموبايل (fields_screen) يضبط مركز/تكبير الخريطة على حقل المستخدم
من geometry المُعاد ضمن fields_summary. هذا الاختبار يثبّت أنّ _shape_indicators_dashboard
يُمرّر geometry لكلّ حقل (مع فكّ JSONB النصّيّ) دون أن يكسر بقيّة العقد
(fields_summary / kpis / alerts) — دالّة نقيّة بلا قاعدة بيانات (CI-enforced).
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def app_mod():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    # _shape_indicators_dashboard نُقِل إلى api.analytics_shapers (تفكيك B1) — دالّة
    # نقيّة بلا fastapi/قاعدة، فلا حاجة لتخطّي fastapi بعد اليوم.
    import api.analytics_shapers as m

    return m


_POLY = {
    "type": "Polygon",
    "coordinates": [[[44.2, 15.3], [44.3, 15.3], [44.3, 15.4], [44.2, 15.3]]],
}


def test_dashboard_includes_geometry_dict(app_mod):
    """geometry يُمرَّر كما هو حين يكون كائناً (dict)، وعلامة الموسم النشط تُحسب."""
    rows = [
        {"field_id": "f1", "name": "حقل القمح", "crop": "wheat", "area_ha": 3.0, "geometry": _POLY}
    ]
    out = app_mod._shape_indicators_dashboard(
        fields_rows=rows, active_field_ids={"f1"}, alert_rows=[]
    )
    assert "fields_summary" in out and "kpis" in out and "alerts" in out
    fs = out["fields_summary"][0]
    assert fs["field_id"] == "f1"
    assert fs["geometry"] == _POLY
    assert fs["has_active_season"] is True
    assert fs["area_ha"] == 3.0


def test_dashboard_unpacks_jsonb_string_geometry(app_mod):
    """JSONB قد يعود نصّاً ⇒ يُفكّ إلى dict؛ والنصّ الفاسد ⇒ None (لا انهيار)."""
    import json

    rows = [
        {
            "field_id": "f2",
            "name": "ب",
            "crop": None,
            "area_ha": None,
            "geometry": json.dumps(_POLY),
        },
        {"field_id": "f3", "name": "ج", "crop": "maize", "area_ha": 1.5, "geometry": "{not-json"},
    ]
    out = app_mod._shape_indicators_dashboard(
        fields_rows=rows, active_field_ids=set(), alert_rows=[]
    )
    by_id = {f["field_id"]: f for f in out["fields_summary"]}
    assert by_id["f2"]["geometry"] == _POLY  # نصّ JSON صالح ⇒ dict
    assert by_id["f3"]["geometry"] is None  # نصّ فاسد ⇒ None رشيق
    assert by_id["f2"]["area_ha"] == 0.0  # area_ha غائب ⇒ 0.0
