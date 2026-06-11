"""اختبارات نقطة المواسم (POST/GET /api/v1/fields/{id}/seasons) — أجزاء صرفة.

تغطّي: تطبيع صفّ DB → SeasonSummary (فكّ crops/stages من JSONB نصّاً + تواريخ
→ ISO)، ودفاعات النموذج، ومجموعة أنواع الريّ. لا حاجة لقاعدة بيانات.
"""

import datetime as _dt
import json

from api.main import (
    _IRRIGATION_TYPES,
    SeasonCreateRequest,
    StageItem,
    _row_to_season,
)


def test_irrigation_types_cover_ui_options():
    # تطابق IRRIGATION_TYPES في الواجهة
    assert _IRRIGATION_TYPES == {"drip", "pivot", "flood", "sprinkler", "rainfed", "subsurface"}


def test_row_to_season_parses_jsonb_and_dates():
    row = {
        "season_id": "ssn_abc",
        "field_id": "fld_1",
        "crops": json.dumps(["قمح صلب", "برسيم"]),  # JSONB يرجع نصّاً
        "cultivar": "صنف محلّي",
        "irrigation_type": "drip",
        "seed_rate_kg_ha": 120.0,
        "land_leveling_date": _dt.date(2026, 1, 1),
        "plowing_date": _dt.date(2026, 1, 5),
        "sowing_date": _dt.date(2026, 1, 10),
        "season_end": _dt.date(2026, 5, 1),
        "stages": json.dumps([{"name": "الرية الأولى", "date": "2026-02-01", "notes": ""}]),
        "status": "active",
        "created_at": _dt.datetime(2026, 1, 1, 12, 0, 0),
    }
    s = _row_to_season(row)
    assert s.season_id == "ssn_abc"
    assert s.crops == ["قمح صلب", "برسيم"]  # فُكّ من JSONB
    assert s.cultivar == "صنف محلّي"
    assert s.irrigation_type == "drip"
    assert s.seed_rate_kg_ha == 120.0
    assert s.sowing_date == "2026-01-10"  # date → ISO
    assert s.season_end == "2026-05-01"
    assert s.stages[0]["name"] == "الرية الأولى"
    assert s.status == "active"


def test_row_to_season_handles_null_dates():
    row = {
        "season_id": "ssn_x",
        "field_id": "fld_1",
        "crops": [],  # قد ترجع list مباشرةً
        "cultivar": None,
        "irrigation_type": None,
        "seed_rate_kg_ha": None,
        "land_leveling_date": None,
        "plowing_date": None,
        "sowing_date": None,
        "season_end": None,
        "stages": [],
        "status": "planned",
        "created_at": None,
    }
    s = _row_to_season(row)
    assert s.crops == []
    assert s.seed_rate_kg_ha is None
    assert s.sowing_date is None
    assert s.created_at is None


def test_season_request_defaults():
    req = SeasonCreateRequest()
    assert req.crops == []
    assert req.custom_stages == []
    assert req.cultivar is None


def test_season_request_negative_seed_rate_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SeasonCreateRequest(seed_rate_kg_ha=-5)


def test_stage_item_serializes():
    st = StageItem(name="الحصاد", date="2026-05-01", notes="يدوي")
    assert st.model_dump() == {"name": "الحصاد", "date": "2026-05-01", "notes": "يدوي"}
