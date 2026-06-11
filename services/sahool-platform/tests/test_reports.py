"""اختبارات تشكيل التقارير (Reports & Analytics) — دوالّ صرفة، بلا قاعدة.

تغطّي تجميع الصفوف النقيّ خلف نقاط /api/v1/reports/*:
  - _count_by_key: صفوف GROUP BY → قاموس {قيمة: عدد} (None ⇒ 'unknown').
  - _shape_area_by_crop: صفوف ({crop, total_area_ha}) → قائمة مُرتّبة بالمساحة.
  - _shape_farm_summary: بناء جسم الملخّص + اشتقاق activities_total.
لا حاجة لاتّصال قاعدة — كلّ دالّة تستقبل صفوفاً (dict) جاهزة.
"""

from api.main import _count_by_key, _shape_area_by_crop, _shape_farm_summary


# ── _count_by_key ────────────────────────────────────────────────
def test_count_by_key_groups_and_casts_to_int():
    rows = [
        {"status": "planned", "count": 3},
        {"status": "done", "count": 2},
    ]
    assert _count_by_key(rows, "status") == {"planned": 3, "done": 2}


def test_count_by_key_empty_rows_is_empty_dict():
    assert _count_by_key([], "status") == {}


def test_count_by_key_none_label_becomes_unknown_and_merges():
    rows = [
        {"activity_type": None, "count": 1},
        {"activity_type": None, "count": 4},
        {"activity_type": "irrigation", "count": 2},
    ]
    assert _count_by_key(rows, "activity_type") == {"unknown": 5, "irrigation": 2}


def test_count_by_key_handles_none_count_as_zero():
    rows = [{"status": "active", "count": None}]
    assert _count_by_key(rows, "status") == {"active": 0}


# ── _shape_area_by_crop ──────────────────────────────────────────
def test_shape_area_by_crop_sorts_desc_and_rounds():
    rows = [
        {"crop": "قمح", "total_area_ha": 1.005},
        {"crop": "ذرة", "total_area_ha": 12.5},
        {"crop": "بطاطس", "total_area_ha": 7.234},
    ]
    out = _shape_area_by_crop(rows)
    assert [r["crop"] for r in out] == ["ذرة", "بطاطس", "قمح"]
    assert out[0]["area_ha"] == 12.5
    assert out[2]["area_ha"] == 1.0


def test_shape_area_by_crop_null_crop_labelled_and_null_area_zeroed():
    rows = [{"crop": None, "total_area_ha": None}]
    out = _shape_area_by_crop(rows)
    assert out == [{"crop": "غير محدّد", "area_ha": 0.0}]


def test_shape_area_by_crop_empty_is_empty_list():
    assert _shape_area_by_crop([]) == []


# ── _shape_farm_summary ──────────────────────────────────────────
def test_shape_farm_summary_derives_total_and_rounds_area():
    out = _shape_farm_summary(
        farms_count=2,
        fields_count=5,
        total_area_ha=42.567,
        active_seasons_count=3,
        activities_by_status={"planned": 4, "done": 6},
        open_alerts_count=1,
        area_by_crop=[{"crop": "قمح", "area_ha": 42.57}],
    )
    assert out["farms_count"] == 2
    assert out["fields_count"] == 5
    assert out["total_area_ha"] == 42.57
    assert out["active_seasons_count"] == 3
    assert out["activities_total"] == 10  # مُشتقّ من مجموع التفصيل
    assert out["activities_by_status"] == {"planned": 4, "done": 6}
    assert out["open_alerts_count"] == 1
    assert out["area_by_crop"] == [{"crop": "قمح", "area_ha": 42.57}]


def test_shape_farm_summary_handles_none_counts_and_empty_activities():
    out = _shape_farm_summary(
        farms_count=None,
        fields_count=None,
        total_area_ha=None,
        active_seasons_count=None,
        activities_by_status={},
        open_alerts_count=None,
        area_by_crop=[],
    )
    assert out["farms_count"] == 0
    assert out["fields_count"] == 0
    assert out["total_area_ha"] == 0.0
    assert out["active_seasons_count"] == 0
    assert out["activities_total"] == 0
    assert out["open_alerts_count"] == 0
