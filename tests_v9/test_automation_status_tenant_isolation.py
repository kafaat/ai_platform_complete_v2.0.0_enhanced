"""R-H1: حالة أتمتة الصور/الطقس لا تكشف حقول المستأجرين الآخرين.

``GET /api/v1/automation/imagery/status`` كان يُعيد المتعقِّب المشترك كلّه لأيّ مستخدم
مُصادَق — معرّفات حقول كلّ المستأجرين وحدودها الدقيقة. وشقيقه ``weather/status`` كان
يُعيد كلّ الإحداثيّات المتتبَّعة وطقسها. هذه الاختبارات تثبّت:
  • مستخدم المستأجِر يرى حقول مستأجِره وحدها في حالة الصور.
  • حالة الطقس لغير مدير المنصّة عدّاداتٌ مجمَّعة بلا إحداثيّات.
  • العرض الكامل لمدير المنصّة (``PLATFORM_MANAGE``) صراحةً.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_CORE = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"
_TENANT_A = "00000000-0000-0000-0000-0000000000a1"
_TENANT_B = "00000000-0000-0000-0000-0000000000b2"
_B_BBOX = [44.123456, 15.234567, 44.125, 15.236]


def _load():
    if str(_CORE) not in sys.path:
        sys.path.insert(0, str(_CORE))
    import api.main  # noqa: F401 — يحلّ دورة استيراد الموجِّهات
    import api.routers.automation as automation

    return automation


def _user(role: str, tenant: str):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(user_id="u-" + role, tenant_id=tenant, role=UserRole(role), name_ar="")


@pytest.fixture
def trackers(monkeypatch):
    automation = _load()
    from api.imagery_automation import ImageryAutomation
    from api.weather_automation import WeatherAutomation

    ia = ImageryAutomation()
    ia.register_field("f-a", [44.0, 15.0, 44.01, 15.01], tenant_id=_TENANT_A)
    ia.register_field("f-b-secret", list(_B_BBOX), tenant_id=_TENANT_B)
    ia.register_field("f-orphan", [43.0, 14.0, 43.01, 14.01], tenant_id=None)

    wa = WeatherAutomation()
    wa.register_location(15.234567, 44.123456, "f-b-secret")
    from api.weather_automation import CachedWeather

    wa._cache[wa._key(15.234567, 44.123456)] = CachedWeather(15.234567, 44.123456, {"t": 30}, 0.0)

    monkeypatch.setattr(automation, "imagery_automation", ia)
    monkeypatch.setattr(automation, "weather_automation", wa)
    return automation


def test_imagery_status_only_shows_callers_tenant_fields(trackers):
    out = trackers.imagery_automation_status_endpoint(user=_user("owner", _TENANT_A))
    ids = [f["field_id"] for f in out["fields"]]
    assert ids == ["f-a"]
    assert out["tracked_fields"] == 1
    assert "f-b-secret" not in repr(out)
    assert "44.123456" not in repr(out)
    assert "raster_service_url" not in out


def test_weather_status_is_aggregate_for_tenant_users(trackers):
    out = trackers.weather_automation_status_endpoint(user=_user("manager", _TENANT_A))
    assert "entries" not in out
    assert out["registered_locations"] == 1
    assert out["cached_entries"] == 1
    assert "44.123456" not in repr(out)
    assert "15.234567" not in repr(out)


def test_platform_admin_keeps_full_view(trackers):
    admin = _user("platform_admin", _TENANT_A)
    img = trackers.imagery_automation_status_endpoint(user=admin)
    assert {f["field_id"] for f in img["fields"]} == {"f-a", "f-b-secret", "f-orphan"}
    wx = trackers.weather_automation_status_endpoint(user=admin)
    assert len(wx["entries"]) == 1
