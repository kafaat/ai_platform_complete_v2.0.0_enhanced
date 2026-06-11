"""اختبارات نقطة العمليّات (POST/GET /api/v1/fields/{id}/activities) — أجزاء صرفة.

تغطّي: تطبيع صفّ DB → ActivitySummary (فكّ details من JSONB كائناً + تواريخ
→ ISO)، ودفاعات النموذج، ومجموعة أنواع العمليّات. لا حاجة لقاعدة بيانات.
"""

import datetime as _dt
import json

from api.main import (
    _ACTIVITY_TYPES,
    ActivityCreateRequest,
    _row_to_activity,
)


def test_activity_types_cover_ui_options():
    assert _ACTIVITY_TYPES == {
        "planting",
        "fertilization",
        "irrigation",
        "spraying",
        "pruning",
        "harvest",
        "scouting",
    }


def test_row_to_activity_parses_jsonb_and_dates():
    row = {
        "activity_id": "act_abc",
        "field_id": "fld_1",
        "season_id": "ssn_1",
        "activity_type": "fertilization",
        "title_ar": "تسميد آزوتي",
        "details": json.dumps({"product": "يوريا", "rate_kg_ha": 50}),  # JSONB يرجع نصّاً
        "scheduled_for": _dt.date(2026, 3, 1),
        "performed_on": _dt.date(2026, 3, 2),
        "status": "done",
        "created_at": _dt.datetime(2026, 3, 1, 9, 0, 0),
    }
    a = _row_to_activity(row)
    assert a.activity_id == "act_abc"
    assert a.field_id == "fld_1"
    assert a.season_id == "ssn_1"
    assert a.activity_type == "fertilization"
    assert a.title_ar == "تسميد آزوتي"
    assert a.details == {"product": "يوريا", "rate_kg_ha": 50}  # فُكّ من JSONB
    assert a.scheduled_for == "2026-03-01"  # date → ISO
    assert a.performed_on == "2026-03-02"
    assert a.status == "done"
    assert a.created_at == "2026-03-01T09:00:00"


def test_row_to_activity_handles_null_dates_and_dict_details():
    row = {
        "activity_id": "act_x",
        "field_id": "fld_1",
        "season_id": None,
        "activity_type": "scouting",
        "title_ar": None,
        "details": {},  # قد ترجع dict مباشرةً
        "scheduled_for": None,
        "performed_on": None,
        "status": "planned",
        "created_at": None,
    }
    a = _row_to_activity(row)
    assert a.season_id is None
    assert a.title_ar is None
    assert a.details == {}
    assert a.scheduled_for is None
    assert a.performed_on is None
    assert a.created_at is None


def test_activity_request_defaults():
    req = ActivityCreateRequest(activity_type="irrigation")
    assert req.activity_type == "irrigation"
    assert req.details == {}
    assert req.title_ar is None
    assert req.scheduled_for is None
    assert req.performed_on is None
    assert req.season_id is None


def test_activity_request_requires_type():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ActivityCreateRequest()


def test_activity_request_keeps_details_dict():
    req = ActivityCreateRequest(
        activity_type="spraying",
        title_ar="رشّ مبيد",
        details={"pesticide": "X", "dose": 1.5},
    )
    assert req.details == {"pesticide": "X", "dose": 1.5}
