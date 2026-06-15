"""اختبارات سجلّ الأحداث (Event Catalog) — مصدر واحد لأنواع أحداث النطاق.

تتحقّق من أنّ السجلّ يضمّ الأحداث الأساسيّة المُصدَرة فعلاً، وأنّ دوال الوصول
(get_event/is_registered/...) سليمة، وأنّ كلّ مدخل متماسك (اسم/فئة/وصف غير فارغة).
"""

from api.event_catalog import (
    get_event,
    is_registered,
    known_event_names,
    list_events,
)


def test_core_verified_events_present():
    # أحداث تحقّقنا من إصدارها في api/main.py — يجب أن تكون مسجَّلة.
    for name in ("FIELD_CREATED", "SEASON_CREATED", "ALERT_CREATED", "ACTIVITY_RECORDED"):
        assert is_registered(name), f"حدث أساسيّ مفقود من السجلّ: {name}"


def test_get_event_returns_full_record():
    ev = get_event("FIELD_CREATED")
    assert ev is not None
    assert ev["name"] == "FIELD_CREATED"
    assert ev["category"] == "field"
    assert ev["version"] >= 1
    assert ev["description_ar"]
    # FIELD_CREATED له حقول حمولة موثّقة (قُرئت من نداء الإصدار الفعليّ).
    assert "area_ha" in ev["payload_keys"]


def test_get_event_unknown_returns_none():
    # لا اختراع: نوع غير مسجَّل ⇒ None لا قاموس وهميّ.
    assert get_event("DOES_NOT_EXIST") is None


def test_is_registered_correct():
    assert is_registered("SEASON_CLOSED") is True
    assert is_registered("nope.not.real") is False


def test_known_event_names_sorted_and_unique():
    names = known_event_names()
    assert names == sorted(names)
    assert len(names) == len(set(names)), "أسماء أحداث مكرّرة"


def test_list_events_matches_known_names():
    events = list_events()
    names = known_event_names()
    assert len(events) == len(names)
    # مرتّبة بالاسم ومطابِقة لمجموعة الأسماء المعروفة.
    assert [e["name"] for e in events] == names


def test_every_entry_has_non_empty_name_category_description():
    for ev in list_events():
        assert ev["name"], "اسم فارغ"
        assert ev["category"], f"فئة فارغة لـ{ev['name']}"
        assert ev["description_ar"], f"وصف فارغ لـ{ev['name']}"


def test_ids_unique():
    # كلّ اسم نوع حدث فريد (المعرّف الوحيد للحدث في السجلّ).
    names = [e["name"] for e in list_events()]
    assert len(names) == len(set(names))


def test_irrigation_valve_events_registered_by_member_name():
    # حدثا الصمّامات مسجَّلان باسم عضو EventType (بأحرف كبيرة) تماشياً مع سائر السجلّ.
    assert is_registered("IRRIGATION_VALVE_REGISTERED")
    assert is_registered("IRRIGATION_VALVE_STATE_CHANGED")
    assert get_event("IRRIGATION_VALVE_REGISTERED")["category"] == "irrigation"


def test_irrigation_valve_names_are_valid_event_type_members():
    # أسماء حدثَي الصمّامات في السجلّ أعضاء صحيحة في EventType.
    from api.event_bus import EventType

    for name in ("IRRIGATION_VALVE_REGISTERED", "IRRIGATION_VALVE_STATE_CHANGED"):
        assert get_event(name)["name"] in EventType.__members__
