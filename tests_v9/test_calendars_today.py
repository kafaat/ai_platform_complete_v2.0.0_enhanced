"""نقطة التقويم الزراعيّ الموحّدة /api/v1/calendars/today — تُبرز ميزة موجودة
(المنازل القمريّة/الأنواء/الحميريّ + نافذة الزراعة) في نداء واحد لبطاقة الواجهة.

تثبّت: التركيب الصحيح + الوسم الصادق (display_only، خارج محرّك القرار) + إدراج
نافذة الزراعة عند تمرير محصول + تعامل التاريخ غير الصالح + تسجيل النقطة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def m():
    added = CORE not in sys.path
    if added:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as main_mod

    # المعالِج calendars_today انتقل إلى api/routers/calendars.py بعد تفكيك monolith؛
    # نوفّره على نسق الوصول القديم m.calendars_today (نفس الدالّة، موقعها فقط تغيّر).
    if not hasattr(main_mod, "calendars_today"):
        from api.routers import calendars as _cal

        main_mod.calendars_today = _cal.calendars_today

    yield main_mod
    if added and CORE in sys.path:
        sys.path.remove(CORE)


def test_today_composes_context_and_honest_flags(m):
    r = m.calendars_today(date="2026-08-27", crop="wheat")
    # وسم صادق محفوظ: عرض فقط، خارج محرّك القرار
    assert r["display_only"] is True
    assert r["used_in_decision_engine"] is False
    # منزلة قمريّة نشطة + جسر النوء/المثل
    assert r["active_mansion"] and r["active_mansion"]["name_ar"]
    assert r["marker_for_proverbs"]
    # نافذة الزراعة للمحصول
    assert "planting" in r
    assert "window" in r["planting"] and "current_month_fit" in r["planting"]


def test_today_without_crop_omits_planting(m):
    r = m.calendars_today(date="2026-08-27")
    assert "planting" not in r
    assert r["active_mansion"] is not None


def test_today_bad_date_returns_error(m):
    r = m.calendars_today(date="not-a-date")
    assert "error_ar" in r


def test_today_bad_date_with_crop_omits_planting(m):
    """تاريخ غير صالح + محصول ⇒ خطأ فقط، بلا planting مشتقّ من تاريخ بديل."""
    r = m.calendars_today(date="not-a-date", crop="wheat")
    assert "error_ar" in r
    assert "planting" not in r


def test_today_route_registered(m):
    from conftest import registered_paths

    assert "/api/v1/calendars/today" in registered_paths(m.app)
