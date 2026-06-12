"""اختبارات «مساحة عمل الحقل» (offline) — طبقات صادقة + خطّ زمنيّ مرتّب.

يتحقّق من: توفّر الطبقات الصادق (متاحة من الأعمدة / عند الطلب للأقمار / غير
متوفّرة)، تطبيع الخطّ الزمنيّ من أحداث مسجّلة فقط (الأحدث أوّلاً) بتسمية عربيّة،
وأنّ التجميع طبقة عرض (display_only). لا قاعدة/شبكة.
"""

from core.engines.field_workspace import (
    assemble_workspace,
    layer_availability,
    normalize_timeline,
)


def _field():
    return {
        "field_id": "f1",
        "name": "حقل وادي سبأ",
        "crop": "wheat",
        "area_ha": 3.0,
        "soil_type": "loam",
        "elevation_m": 1800.0,
        "slope_pct": 12.0,
        "aspect": "S",
        "water_ec": None,  # ملوحة غير مُدخَلة
        "irrigation_type": "drip",
    }


# ─── توفّر الطبقات (صدق) ─────────────────────────────────────────────────


def test_imagery_layers_are_on_demand_not_fabricated():
    layers = {lyr["key"]: lyr for lyr in layer_availability(_field())}
    # طبقات الأقمار لا تُخزَّن ⇒ عند الطلب، available=False (لا تلوين مفبرك)
    assert layers["ndvi"]["status"] == "on_demand"
    assert layers["ndvi"]["available"] is False
    assert layers["ndmi"]["status"] == "on_demand"


def test_stored_layers_available_from_columns():
    layers = {lyr["key"]: lyr for lyr in layer_availability(_field())}
    assert layers["elevation"]["available"] is True  # elevation_m موجود
    assert layers["slope"]["available"] is True
    assert layers["aspect"]["available"] is True
    assert layers["soil_type"]["available"] is True
    assert layers["irrigation"]["available"] is True


def test_missing_column_layer_is_honestly_unavailable():
    layers = {lyr["key"]: lyr for lyr in layer_availability(_field())}
    assert layers["salinity"]["available"] is False  # water_ec = None
    assert layers["salinity"]["status"] == "missing"


def test_all_layers_are_display_only():
    assert all(lyr["display_only"] for lyr in layer_availability(_field()))


# ─── الخطّ الزمنيّ ────────────────────────────────────────────────────────


def test_timeline_sorted_latest_first_with_arabic_labels():
    events = [
        {"event_type": "field.created", "occurred_at": "2026-01-01T08:00:00"},
        {"event_type": "irrigation.completed", "occurred_at": "2026-03-10T06:00:00"},
        {"event_type": "harvest.completed", "occurred_at": "2026-06-01T05:00:00"},
    ]
    tl = normalize_timeline(events)
    assert tl[0]["event_type"] == "harvest.completed"  # الأحدث أوّلاً
    assert tl[0]["op_ar"] == "حصاد"
    assert tl[0]["category"] == "harvest"
    assert tl[-1]["op_ar"] == "إنشاء الحقل"


def test_timeline_maps_known_operation_categories():
    cases = {
        "planting.completed": ("زراعة", "planting"),
        "fertilizer.applied": ("تسميد", "fertilization"),
        "pesticide.applied": ("رشّ مبيد", "spraying"),
        "season.created": ("بدء موسم", "season"),
        "lifecycle.transitioned": ("انتقال مرحلة", "lifecycle"),
    }
    for et, (op_ar, cat) in cases.items():
        card = normalize_timeline([{"event_type": et, "occurred_at": "2026-01-01T00:00:00"}])[0]
        assert card["op_ar"] == op_ar
        assert card["category"] == cat


def test_empty_events_yield_empty_timeline_no_invention():
    assert normalize_timeline([]) == []  # لا تاريخ مخترَع


def test_issue_tags_normalized_to_list_when_none_or_invalid():
    # issue_tags=None أو نوع غير صالح ⇒ [] (عقد المستهلك: قائمة دائماً)
    for bad in (None, "tag", 5):
        card = normalize_timeline(
            [
                {
                    "event_type": "irrigation.completed",
                    "occurred_at": "2026-01-01T00:00:00",
                    "issue_tags": bad,
                }
            ]
        )[0]
        assert card["issue_tags"] == []


def test_missing_non_terrain_layer_note_does_not_mention_dem():
    # salinity/soil/irrigation لا تُملأ من DEM ⇒ لا توجيه مضلّل
    layers = {lyr["key"]: lyr for lyr in layer_availability({"field_id": "f", "water_ec": None})}
    assert "DEM" not in layers["salinity"]["note_ar"]
    # بينما طبقة تضاريس مفقودة تذكر DEM
    assert "DEM" in layers["elevation"]["note_ar"]


# ─── التجميع الكامل ──────────────────────────────────────────────────────


def test_assemble_workspace_is_display_only_and_complete():
    events = [{"event_type": "irrigation.completed", "occurred_at": "2026-03-10T06:00:00"}]
    ws = assemble_workspace(_field(), {"display_only": True}, events)
    assert ws["display_only"] is True  # طبقة عرض لا قرار
    assert ws["field_id"] == "f1"
    assert ws["field"]["name_ar"] == "حقل وادي سبأ"
    assert ws["available_layer_count"] == 5  # elevation/slope/aspect/soil/irrigation
    assert ws["timeline_total"] == 1
    assert ws["terrain"]["display_only"] is True
    assert "honesty_note_ar" in ws
