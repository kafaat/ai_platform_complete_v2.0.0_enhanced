"""Stage F — تنبيهات مُشتقّة من الحالة القانونيّة الموحّدة (Canonical Field State).

على عكس POST /api/v1/alerts (محتواه من المتّصِل)، النقطة الجديدة
GET /api/v1/fields/{field_id}/alerts/derived تشتقّ تنبيهات صادقة **من الحالة**.

يثبّت الاختبار سلوك دالّة الاشتقاق النقيّة (_derive_alerts_from_state) بلا قاعدة:
ملوحة حرجة ⇒ تنبيه critical، نمط تنفيذ غير تلقائيّ ⇒ تنبيه warning مراجعة بشريّة،
غياب الحقائق ⇒ قائمة فارغة (لا تلفيق) — إضافةً إلى تسجيل النقطة GET.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)


def _derive(core_on_path):
    from api.field_state_projection import _derive_alerts_from_state

    return _derive_alerts_from_state


def test_critical_salinity_yields_high_alert(core_on_path):
    derive = _derive(core_on_path)
    alerts = derive(
        {
            "agronomic": {"operational_truths": {"salinity_class": "critical"}},
            "execution_mode": "auto",
        }
    )
    sal = [a for a in alerts if a["alert_type"] == "salinity_critical"]
    assert len(sal) == 1, "ملوحة حرجة لم تُنتج تنبيهاً"
    assert sal[0]["severity"] == "critical", "تنبيه الملوحة الحرجة ليس critical (عقد المنصّة)"
    assert sal[0]["source"] == "canonical_field_state", "مصدر التنبيه غير موسوم بالحالة الموحّدة"
    assert sal[0]["title_ar"] and sal[0]["message_ar"], "تنبيه بلا عنوان/رسالة عربيّة"


def test_blocked_or_human_review_yields_review_alert(core_on_path):
    derive = _derive(core_on_path)
    for mode in ("blocked", "human_review"):
        alerts = derive({"execution_mode": mode})
        rev = [a for a in alerts if a["alert_type"] == "human_review_required"]
        assert len(rev) == 1, f"نمط {mode} لم يُنتج تنبيه مراجعة بشريّة"
        assert rev[0]["source"] == "canonical_field_state"


def test_no_truths_yields_empty(core_on_path):
    derive = _derive(core_on_path)
    # لا حقائق زراعيّة ونمط تنفيذ تلقائيّ ⇒ لا تنبيه مُلفَّق (صدق).
    assert derive({"execution_mode": "auto"}) == []
    assert derive({}) == []
    assert derive({"agronomic": {"operational_truths": {}}, "execution_mode": "auto"}) == []
    # مدخل غير قاموس ⇒ قائمة فارغة (fail-safe، لا انهيار).
    assert derive(None) == []


def test_derived_alerts_route_registered(core_on_path):
    pytest.importorskip("fastapi")
    import api.main as m

    from conftest import registered_methods

    methods = registered_methods(m.app, "/api/v1/fields/{field_id}/alerts/derived")
    assert "GET" in methods, "نقطة GET /api/v1/fields/{field_id}/alerts/derived غير مُسجَّلة"
