"""اختبارات مستهلِك الموزِّع البشريّ (core.dispatch_notification) — المرحلة A، الشريحة 3.

نقيّة وحتميّة ⇒ `unit`. تثبّت: تطبيع القناة، ترجمة القرار إلى حمولة إخطار صادقة
(عنوان/شدّة/جسم/requires_human_action)، والوصول لمفاتيح الصفّ (dict وكائن).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from core.dispatch_notification import (  # noqa: E402
    CHANNELS,
    build_dispatch_notification,
    normalize_channel,
)


def test_normalize_channel():
    assert normalize_channel("sms") == "sms"
    assert normalize_channel("WhatsApp") == "whatsapp"
    assert normalize_channel("mobile_task") == "mobile_task"
    # مجهول/غائب ⇒ mobile_task (الأقلّ كلفة وأماناً)
    assert normalize_channel("carrier_pigeon") == "mobile_task"
    assert normalize_channel(None) == "mobile_task"
    assert normalize_channel("") == "mobile_task"


def test_channels_constant():
    assert CHANNELS == ("sms", "whatsapp", "mobile_task")


def _row(**kw):
    base = {
        "decision_id": "disp_abc",
        "action_type": "irrigation",
        "field_id": "f1",
        "risk_level": "HIGH",
        "reason_ar": "رطوبة التربة منخفضة",
        "command": {"device_id": "valve_1", "command": "open_valve"},
    }
    base.update(kw)
    return base


def test_build_notification_basic():
    n = build_dispatch_notification(_row(), "sms")
    assert n["channel"] == "sms"
    assert n["severity"] == "critical"  # HIGH ⇒ critical
    assert n["decision_id"] == "disp_abc"
    assert n["action_type"] == "irrigation"
    assert n["field_id"] == "f1"
    assert n["title_ar"] == "إجراء ريّ مطلوب"
    assert "رطوبة التربة منخفضة" in n["body_ar"]
    assert "الحقل f1" in n["body_ar"]
    assert n["requires_human_action"] is True
    assert n["command"]["command"] == "open_valve"


def test_severity_mapping():
    assert build_dispatch_notification(_row(risk_level="LOW"))["severity"] == "info"
    assert build_dispatch_notification(_row(risk_level="MEDIUM"))["severity"] == "warning"
    assert build_dispatch_notification(_row(risk_level="CRITICAL"))["severity"] == "critical"
    # مجهول ⇒ warning (تحفّظ معتدل)
    assert build_dispatch_notification(_row(risk_level="???"))["severity"] == "warning"


def test_title_for_known_actions():
    assert build_dispatch_notification(_row(action_type="spray"))["title_ar"] == "إجراء رشّ مطلوب"
    assert (
        build_dispatch_notification(_row(action_type="defer_irrigation"))["title_ar"]
        == "تأجيل ريّ مطلوب"
    )
    # مجهول ⇒ عنوان عامّ
    assert build_dispatch_notification(_row(action_type="zap"))["title_ar"] == "إجراء زراعيّ مطلوب"


def test_default_channel_when_none():
    assert build_dispatch_notification(_row())["channel"] == "mobile_task"


def test_missing_field_id_no_field_suffix():
    n = build_dispatch_notification(_row(field_id=None, reason_ar="تنبيه"))
    assert "الحقل" not in n["body_ar"]
    assert n["field_id"] is None


def test_reads_object_row_not_just_dict():
    class Row:
        decision_id = "disp_o"
        action_type = "spray"
        field_id = "f9"
        risk_level = "MEDIUM"
        reason_ar = "آفة مكتشفة"
        command = None

        def __getitem__(self, k):  # يحاكي سجلّ asyncpg (Mapping)
            return getattr(self, k)

    n = build_dispatch_notification(Row(), "whatsapp")
    assert n["decision_id"] == "disp_o"
    assert n["title_ar"] == "إجراء رشّ مطلوب"
    assert n["command"] is None
