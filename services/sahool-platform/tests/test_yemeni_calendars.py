"""اختبارات وحدة لإثراء التقاويم اليمنيّة (api/yemeni_calendars.py) — offline.

تغطّي: المنازل القمريّة الـ٢٨، الشهور الحميريّة الـ١٢، الملفّات الإقليميّة (الربط
المكانيّ)، الجسر الزمني (تاريخ→منزلة)، وجسر الأمثال — مع حفظ مبدأ «عرض فقط، لا
يدخل القرار». لا حاجة لقاعدة بيانات.
"""

from api.agricultural_proverbs import proverbs_for_date
from api.yemeni_calendars import (
    calendar_context_for_date,
    get_himyarite_months,
    get_lunar_mansions,
    get_regional_profiles,
)


def test_lunar_mansions_28_display_only():
    d = get_lunar_mansions()
    assert d["count"] == 28
    assert d["display_only"] is True


def test_himyarite_months_12():
    assert get_himyarite_months()["count"] == 12


def test_regional_profiles_spatial_link():
    # الربط المكانيّ: ٤ ملفّات إقليميّة (حضرموت/تهامة/المرتفعات/الجوف)
    d = get_regional_profiles()
    profiles = d.get("profiles", [])
    assert len(profiles) >= 4


def test_context_bridge_never_enters_decisions():
    ctx = calendar_context_for_date("2025-04-15", governorate="حضرموت")
    assert ctx["display_only"] is True
    assert ctx["used_in_decision_engine"] is False


def test_proverbs_for_date_bridge():
    pr = proverbs_for_date("2025-04-15", governorate="حضرموت")
    assert "proverbs" in pr
    assert pr["date_iso"] == "2025-04-15"
