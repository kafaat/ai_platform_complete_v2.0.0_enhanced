"""TYPED-CONTRACT-FORBIDS-ABSENCE-SO-THE-EDGE-INVENTS-ZERO-01 — الغيابُ لا يُختلَق صفراً عند الحافّة.

**العطلُ مقيسٌ بالتنفيذ على الشجرة قبل الإصلاح (`bcb7f0ed`)، لا موصوف:**

- يومٌ بلا `temperature_2m_min` ⇒ `temp_min_c=0` ⇒ `evaluate_field_alerts` يُطلِق
  `frost_risk` بشدّة **critical** — تنبيهٌ يُكتَب ويُرسَل للمزارع من لا قياس.
- قراءةٌ آنيّةٌ بلا `weather_code` ⇒ `0` ⇒ `describe_weather_ar` يقول «صافٍ».
- قراءةٌ آنيّةٌ بلا حرارةٍ ورطوبة ⇒ `0°م`/`0٪` ⇒ خطرُ مرضٍ مُهدَّفٌ ويُعاد ٢٠٠.

شريحةُ المطر (`test_missing_rain_is_not_no_rain.py`) أغلقت المطرَ وحدَه وتركت هذه مُعلَنةً.
**والريحُ خارجُ هذا الملفّ عمداً**: حكمُ غيابها مؤجَّلٌ للمالك
(`PLATFORM-CONNECTOR-STILL-COERCES-AN-ABSENT-WIND-TO-ZERO-01`)، فلا شاهدَ هنا يثبّتها أو يقلبها.

والقياسُ على **مواضع البناء** (`_build_daily` · `fetch_current` · `fetch_current_batch` عبر
`_fetch_json` مُستبدَلاً) لا على المساعِدة `_daily_at` — درسُ شريحة المطر: قياسُ المساعِدة
بافتراضٍ يُمرِّره الاختبارُ بيده نجت منه الطفرة. ولكلّ غيابٍ **صفرٌ مرصودٌ مقابل** يبقى صفراً،
فـ`0°م` حرارةٌ حقيقيّة و`weather_code=0` سماءٌ صافيةٌ رُصِدت.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.alert_rules import FieldAlertContext, evaluate_field_alerts  # noqa: E402
from api.connectors import openmeteo  # noqa: E402

pytestmark = pytest.mark.unit

_DAILY_WITHOUT_TEMPERATURES = {
    "precipitation_sum": [0.0],
    "et0_fao_evapotranspiration": [5.0],
    "wind_speed_10m_max": [3.0],
}

# اتّجاهُ الريح حاضرٌ عمداً: غيابُه يستدعي احتياطَ MET.no الشبكيّ داخل `fetch_current`.
_CURRENT_WITHOUT_READINGS = {"precipitation": 0.0, "wind_direction_10m": 90.0, "time": "t"}


def _stub_fetch(monkeypatch, *, current: dict, daily: dict | None = None) -> None:
    async def fake_fetch_json(url, params, timeout_s):
        if "current" in params:
            return {"current": current}
        return {"daily": {"time": ["2026-03-01"], **(daily or {})}}

    monkeypatch.setattr(openmeteo, "_fetch_json", fake_fetch_json)


# ── ① الحافّة اليوميّة ────────────────────────────────────────────────
def test_the_daily_edge_keeps_absent_temperatures_and_code_absent():
    day = openmeteo._build_daily(_DAILY_WITHOUT_TEMPERATURES, 0, "2026-03-01")
    assert day.temp_max_c is None, "غيابُ العظمى اختُلِق صفراً عند الحافّة"
    assert day.temp_min_c is None, "غيابُ الصغرى اختُلِق صفراً عند الحافّة"
    assert day.weather_code is None, "غيابُ رمز الطقس اختُلِق «صافٍ»"

    observed = openmeteo._build_daily(
        {
            **_DAILY_WITHOUT_TEMPERATURES,
            "temperature_2m_max": [0.0],
            "temperature_2m_min": [-3.5],
            "weather_code": [0],
        },
        0,
        "2026-03-01",
    )
    assert (observed.temp_max_c, observed.temp_min_c, observed.weather_code) == (0.0, -3.5, 0), (
        "صفرٌ مرصودٌ ضاع — `0°م` و`weather_code=0` قياسان لا غياب"
    )


def test_an_absent_minimum_no_longer_raises_a_critical_frost_alert():
    """**الأثرُ المقيس:** قبل الإصلاح هذه الحالةُ نفسُها أعطت `[('frost_risk', 'critical')]`."""
    day = openmeteo._build_daily(_DAILY_WITHOUT_TEMPERATURES, 0, "2026-03-01")
    alerts = evaluate_field_alerts(
        FieldAlertContext(field_id="f", tmax_c=day.temp_max_c, tmin_c=day.temp_min_c)
    )
    assert [a.alert_type for a in alerts if a.alert_type == "frost_risk"] == [], (
        "صقيعٌ حرجٌ من قراءةٍ غائبة"
    )

    # والقاعدةُ ما تزال تعمل على قياسٍ حقيقيّ — فالصمتُ أعلاه ليس تعطيلاً لها.
    cold = openmeteo._build_daily(
        {**_DAILY_WITHOUT_TEMPERATURES, "temperature_2m_min": [-2.0]}, 0, "2026-03-01"
    )
    fired = evaluate_field_alerts(FieldAlertContext(field_id="f", tmin_c=cold.temp_min_c))
    assert any(a.alert_type == "frost_risk" for a in fired)


# ── ② الحافّة الآنيّة ─────────────────────────────────────────────────
async def test_the_current_edge_keeps_absent_readings_absent(monkeypatch):
    _stub_fetch(monkeypatch, current=_CURRENT_WITHOUT_READINGS)
    cur = await openmeteo.fetch_current(15.0, 44.0)
    assert (cur.temperature_c, cur.humidity_pct, cur.cloud_cover_pct, cur.weather_code) == (
        None,
        None,
        None,
        None,
    ), "قراءةٌ آنيّةٌ غائبةٌ اختُلِقت صفراً"
    assert openmeteo.describe_weather_ar(cur.weather_code) == "غير معروف"
    assert openmeteo.describe_weather_ar(0) == openmeteo.WMO_DESCRIPTIONS_AR[0] != "غير معروف", (
        "رمزٌ مرصود `0` فقد وصفَه"
    )

    _stub_fetch(
        monkeypatch,
        current={
            **_CURRENT_WITHOUT_READINGS,
            "temperature_2m": 0.0,
            "relative_humidity_2m": 0.0,
            "cloud_cover": 0.0,
            "weather_code": 0,
        },
    )
    zero = await openmeteo.fetch_current(15.0, 44.0)
    assert (zero.temperature_c, zero.humidity_pct, zero.cloud_cover_pct, zero.weather_code) == (
        0.0,
        0.0,
        0.0,
        0,
    ), "صفرٌ مرصودٌ ضاع"


async def test_the_batch_edge_is_held_to_the_same_contract(monkeypatch):
    """`fetch_current_batch` موضعُ بناءٍ ثانٍ لـ`CurrentWeather` — نسيانُه يُبقي نصفَ الحافّة كاذباً."""

    async def fake_fetch_json(url, params, timeout_s):
        return [{"current": _CURRENT_WITHOUT_READINGS}, {"current": _CURRENT_WITHOUT_READINGS}]

    monkeypatch.setattr(openmeteo, "_fetch_json", fake_fetch_json)
    out = await openmeteo.fetch_current_batch([(15.0, 44.0), (16.0, 45.0)])
    assert out, "الدفعةُ لم تُرجِع شيئاً — تغيّر شكلُ الردّ، حدِّث الشاهدَ لا الادّعاء"
    for cur in out:
        assert cur is not None
        assert (cur.temperature_c, cur.humidity_pct, cur.cloud_cover_pct, cur.weather_code) == (
            None,
            None,
            None,
            None,
        ), "الدفعةُ تختلق صفراً حيث المفردُ لا يختلق"


# ── ③ المستهلك: خطرُ المرض يفشل مغلقاً لا يُهدِّف ────────────────────
async def test_disease_risk_refuses_to_score_absent_temperature_and_humidity(monkeypatch):
    """قبل الإصلاح: ٢٠٠ بخطرٍ مُهدَّفٍ من `0°م`/`0٪`. الآن: ٥٠٣ يُسمّي الناقص."""
    from contextlib import asynccontextmanager

    from api.routers import fields
    from fastapi import HTTPException

    @asynccontextmanager
    async def fake_conn(user):
        yield None

    async def fake_context(conn, field_id):
        return 15.0, 44.0, "tomato", "mid", 60

    monkeypatch.setattr(fields, "tenant_connection", fake_conn)
    monkeypatch.setattr(fields, "_field_weather_context", fake_context)
    _stub_fetch(
        monkeypatch,
        current=_CURRENT_WITHOUT_READINGS,
        daily={"precipitation_sum": [1.0, 2.0, 3.0], "time": ["a", "b", "c"]},
    )
    with pytest.raises(HTTPException) as ei:
        await fields.field_disease_risk("f1", user=None)
    assert ei.value.status_code == 503
    assert "الحرارة" in str(ei.value.detail)


def test_the_spray_judgement_does_not_turn_an_absent_temperature_into_permission():
    """`spraying_condition_score` بلا مستدعٍ اليوم — لكنّه عقدٌ عامّ، فلا يُترَك يرمي أو يأذن.

    قبل الإصلاح: `temp_max_c=None` ⇒ `TypeError` في `> 35`؛ ولو بقيت صفراً لأعطى «ظروف مناسبة».
    """
    day = openmeteo._build_daily(_DAILY_WITHOUT_TEMPERATURES, 0, "2026-03-01")
    status, reason = openmeteo.spraying_condition_score(day)
    assert status == "unknown" and "الحرارة" in reason

    measured = openmeteo._build_daily(
        {**_DAILY_WITHOUT_TEMPERATURES, "temperature_2m_max": [30.0]}, 0, "2026-03-01"
    )
    assert openmeteo.spraying_condition_score(measured)[0] != "unknown"
