"""اختبارات نقطة التنبيهات (GET/POST /api/v1/alerts + PATCH ack) — أجزاء صرفة.

تغطّي: تطبيع صفّ DB → AlertSummary (تواريخ → ISO، حقل اختياريّ)، ودفاعات
النموذج، ومجموعات الأنواع/الخطورة/الحالة. لا حاجة لقاعدة بيانات.
"""

import datetime as _dt

from api.alert_models import (
    _ALERT_SEVERITIES,
    _ALERT_STATUSES,
    _ALERT_TYPES,
    AlertCreateRequest,
    _row_to_alert,
)


def test_alert_types_cover_ui_options():
    assert _ALERT_TYPES == {
        "low_moisture",
        "heavy_rain",
        "disease_risk",
        "heat_stress",
        "frost_risk",
        "other",
    }


def test_alert_severities_and_statuses():
    assert _ALERT_SEVERITIES == {"info", "warning", "critical"}
    assert _ALERT_STATUSES == {"active", "acknowledged", "resolved"}


def test_row_to_alert_maps_fields_and_isoformats_created_at():
    row = {
        "alert_id": "alr_abc",
        "field_id": "fld_1",
        "alert_type": "low_moisture",
        "severity": "warning",
        "title_ar": "رطوبة منخفضة",
        "message_ar": "رطوبة التربة دون الحدّ الأدنى",
        "status": "active",
        "created_at": _dt.datetime(2026, 3, 1, 9, 0, 0),
    }
    a = _row_to_alert(row)
    assert a.alert_id == "alr_abc"
    assert a.field_id == "fld_1"
    assert a.alert_type == "low_moisture"
    assert a.severity == "warning"
    assert a.title_ar == "رطوبة منخفضة"
    assert a.message_ar == "رطوبة التربة دون الحدّ الأدنى"
    assert a.status == "active"
    assert a.created_at == "2026-03-01T09:00:00"


def test_row_to_alert_handles_null_field_and_created_at():
    row = {
        "alert_id": "alr_x",
        "field_id": None,  # تنبيه على مستوى المستأجِر بلا حقل
        "alert_type": "frost_risk",
        "severity": "critical",
        "title_ar": None,
        "message_ar": None,
        "status": "acknowledged",
        "created_at": None,
    }
    a = _row_to_alert(row)
    assert a.field_id is None
    assert a.title_ar is None
    assert a.message_ar is None
    assert a.status == "acknowledged"
    assert a.created_at is None


def test_alert_request_defaults():
    req = AlertCreateRequest(alert_type="heavy_rain", severity="info")
    assert req.alert_type == "heavy_rain"
    assert req.severity == "info"
    assert req.title_ar is None
    assert req.message_ar is None
    assert req.field_id is None


def test_alert_request_requires_type_and_severity():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AlertCreateRequest(severity="info")  # نوع ناقص
    with pytest.raises(ValidationError):
        AlertCreateRequest(alert_type="heat_stress")  # خطورة ناقصة


def test_alert_request_keeps_fields():
    req = AlertCreateRequest(
        alert_type="disease_risk",
        severity="critical",
        title_ar="خطر مرض",
        message_ar="ظروف ملائمة لانتشار الفطريّات",
        field_id="fld_9",
    )
    assert req.alert_type == "disease_risk"
    assert req.severity == "critical"
    assert req.title_ar == "خطر مرض"
    assert req.message_ar == "ظروف ملائمة لانتشار الفطريّات"
    assert req.field_id == "fld_9"
