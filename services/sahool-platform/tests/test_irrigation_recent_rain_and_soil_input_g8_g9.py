"""G8 + G9 — مدخلا توصية الريّ في مساحة العمل: «المطر الأخير» ورطوبة التربة.

**G8:** كان `field_irrigation_advice_facade` يأخذ ``current.precipitation_mm`` — مطرَ
آخر ربع ساعة — ويطرحه من احتياج يومٍ كامل، بينما مسارُ التوصية الموحَّدة
(`field_irrigation_weather_snapshot`) يأخذ مجموعَ يومِ ET₀ (``days[0]``). يومٌ أمطر
صباحاً ثمّ صحا يُعطي ريّاً في مسارٍ ولا ريّ في الآخر. الآن تعريفٌ واحد:
``weather_advice.irrigation_rain_window``.

**ومراجعة #1329:** ``days[0]`` هو ``precipitation_sum`` ليومٍ محلّيٍّ **كامل** من
التوقّع — يضمّ مطرَ ما تبقّى من اليوم الذي لم يهطل بعد. فلا يُخصَم «أخيراً»: لا رصدَ
مُنقضياً في هذا المسار ⇒ ``recent = 0.0`` بوسمٍ صريح، ومطرُ اليوم كلُّه في نافذة التوقّع.

**G9:** كانت القراءةُ تُمرَّر ``value_pct`` عارية: ``25٪ VWC`` تُقرأ «ماءً متاحاً ٢٥٪»
(< ٣٠ ⇒ ريٌّ عاجل ``high``)، وقراءةُ ساعاتٍ مضت تُعامَل قراءةَ الآن.

الأرقامُ مُثبَّتة: قمح يوم ٨٠ (``mid``، Kc = 1.15)، ET₀ = 5.0 ⇒ ETc = 5.75 مم.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from api.soil_telemetry import SoilMoistureReading, irrigation_soil_input
from api.weather_advice import RAIN_RECENT_NOT_OBSERVED, irrigation_rain_window

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


# ── G8: التعريفُ الواحد ───────────────────────────────────────────────
def test_the_rain_window_never_deducts_forecast_rain_and_names_its_gaps():
    # مطرُ اليوم توقّعٌ ليومٍ كامل لا رصد ⇒ لا يُخصَم؛ يدخل نافذةَ التوقّع مع اليومين التاليين.
    # (كان ``(3.0, 3.0, [])`` — أي أنّ المتوقَّعَ لما تبقّى من اليوم يُخصَم «مطراً أخيراً».)
    assert irrigation_rain_window([3.0, 1.0, 2.0]) == (0.0, 6.0, [])
    assert irrigation_rain_window([0.0, 0.0, 0.0]) == (0.0, 0.0, [])
    # الغيابُ يُسمّى بفهارس `precipitation_incomplete_detail` نفسِها — لا يُصفَّر.
    assert irrigation_rain_window([None, 1.0, None]) == (0.0, None, [0, 2])
    assert irrigation_rain_window([]) == (0.0, None, [0, 1, 2])


def _patch_workspace(monkeypatch, *, forecast_days, current_rain=0.0, soil=None):
    """يُبدِّل فاصلَ مُدخلات القاعدة (سياقُ الحقل + آخرُ قراءة رطوبة) لا مُورِّدَ الاتّصال.

    القرارُ المُختبَر كلُّه بعد هذا الفاصل؛ فلا اتّصالَ وهميّاً يدّعي ما تفرضه القاعدة.
    """
    import api.routers.field_workspace_weather as wmod

    async def _inputs(_user, _field_id):
        return (16.0, 44.9, "wheat", "mid", 80, soil)

    async def _forecast(_lat, _lon, days=3):
        return {"days": forecast_days}

    async def _current(_lat, _lon):
        return {"precipitation_mm": current_rain}

    monkeypatch.setattr(wmod, "_irrigation_field_inputs", _inputs)
    monkeypatch.setattr(wmod, "get_weather_forecast", _forecast)
    monkeypatch.setattr(wmod, "get_current_weather", _current)
    return wmod


@pytest.mark.asyncio
async def test_workspace_does_not_deduct_the_forecast_days_total_as_recent_rain(monkeypatch):
    """يومٌ مجموعُ توقّعه ٣ مم: لا يُعرَف أهطل صباحاً أم يُنتظَر مساءً — فلا يُخصَم.

    كان هذا الاختبارُ يُثبِّت ``2.8`` و``low`` (خصمُ 2.99 مم من مجموع اليوم المتوقَّع) —
    وهو العطلُ نفسُه الذي سمّته مراجعة #1329. الآن: ETc 5.75 ⇒ ``5.8`` و``moderate``،
    و٣ مم في نافذة التوقّع (< ٥ ⇒ لا تأجيل).
    """
    forecast_days = [
        {"et0_mm": 5.0, "precipitation_mm": 3.0},
        {"et0_mm": 5.0, "precipitation_mm": 0.0},
        {"et0_mm": 5.0, "precipitation_mm": 0.0},
    ]
    wmod = _patch_workspace(monkeypatch, forecast_days=forecast_days, current_rain=0.0)
    out = await wmod.field_irrigation_advice_facade("fld_1", user=object())
    assert out["kc_used"] == pytest.approx(1.15)
    assert out["recommended_mm"] == pytest.approx(5.8)
    assert out["urgency"] == "moderate"
    assert out["rain_recent_source"] == RAIN_RECENT_NOT_OBSERVED

    # والمسارُ الآخر يقرأ المطرَ نفسَه من الحمولة نفسِها — لا توصيتان لحقلٍ واحد.
    from api.weather_service_client import field_irrigation_weather_snapshot

    async def _loader(_lat, _lon, *, days):
        assert days == 3
        return {"days": [dict(d, date="2026-11-02") for d in forecast_days]}

    snap = await field_irrigation_weather_snapshot(16.0, 44.9, forecast_loader=_loader)
    assert (snap["rain_recent_mm"], snap["forecast_rain_mm"]) == (0.0, 3.0)
    assert snap["rain_recent_source"] == RAIN_RECENT_NOT_OBSERVED


@pytest.mark.asyncio
async def test_unfallen_rain_today_does_not_cancel_irrigation_on_critically_dry_soil(monkeypatch):
    """مراجعة #1329 (HIGH): ١٢ مم متوقَّعة مساءً، وتربةٌ طازجة بماءٍ متاح ٢٠٪ (< ٣٠ حرج).

    قبل الإصلاح: المطرُ الفعّال من مجموع اليوم 11.77 ≥ ETc 5.75 ⇒ ``recommended_mm=0.0``
    و``urgency=none`` «لا حاجة للريّ» — والتربةُ حرجة. بعده: لا خصمَ لمطرٍ لم يهطل ⇒
    ``5.8`` و``high``؛ والـ١٢ مم في نافذة التوقّع لا تؤجّل الحرِج.
    """
    forecast_days = [
        {"et0_mm": 5.0, "precipitation_mm": 12.0},
        {"et0_mm": 5.0, "precipitation_mm": 0.0},
        {"et0_mm": 5.0, "precipitation_mm": 0.0},
    ]
    reading = SoilMoistureReading(
        value_pct=20.0,
        recorded_at=datetime.now(UTC) - timedelta(minutes=20),
        unit="available_pct",
        unit_kind="available_pct",
    )
    wmod = _patch_workspace(monkeypatch, forecast_days=forecast_days, soil=reading)
    out = await wmod.field_irrigation_advice_facade("fld_1", user=object())
    assert out["recommended_mm"] == pytest.approx(5.8)
    assert out["urgency"] == "high"
    assert out["soil_moisture_used"] is True
    assert out["rain_recent_source"] == RAIN_RECENT_NOT_OBSERVED


@pytest.mark.asyncio
async def test_workspace_missing_et0_day_rain_fails_closed_even_if_current_is_dry(monkeypatch):
    """«المطر المفقود ليس لا مطر»: يومُ ET₀ بلا مطر ⇒ 503 يُسمّي الفترة ``0``."""
    from fastapi import HTTPException

    forecast_days = [
        {"et0_mm": 5.0, "precipitation_mm": None},
        {"et0_mm": 5.0, "precipitation_mm": 0.0},
        {"et0_mm": 5.0, "precipitation_mm": 0.0},
    ]
    wmod = _patch_workspace(monkeypatch, forecast_days=forecast_days, current_rain=0.0)
    with pytest.raises(HTTPException) as exc:
        await wmod.field_irrigation_advice_facade("fld_1", user=object())
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "WEATHER_PRECIPITATION_INCOMPLETE"
    assert exc.value.detail["missing_intervals"] == [0]


# ── G9: الوحدةُ والعمر ─────────────────────────────────────────────────
def _reading(*, unit, age, value=25.0):
    return SoilMoistureReading(
        value_pct=value,
        recorded_at=_NOW - age,
        device_id="dev-1",
        unit=unit,
        unit_kind={"vwc_pct": "vwc_pct", "available_pct": "available_pct"}.get(unit, "undeclared"),
    )


def test_soil_input_carries_unit_and_age_and_gates_stale_and_vwc():
    fresh_vwc = irrigation_soil_input(_reading(unit="vwc_pct", age=timedelta(hours=1)), now=_NOW)
    assert fresh_vwc["usable_pct"] == 25.0  # يبلغ المُقرِّر ليُعلِنه غيرَ مُستعمَل
    assert fresh_vwc["soil_moisture_unit_kind"] == "vwc_pct"
    assert fresh_vwc["soil_moisture_age_s"] == 3600.0
    assert fresh_vwc["soil_moisture_freshness"] == "fresh"
    assert fresh_vwc["soil_moisture_used"] is False
    assert fresh_vwc["soil_moisture_limitations"] == [
        "soil_moisture_vwc_not_comparable_to_available_water"
    ]

    # سقفُ الطزاجة ٤ ساعات (`device_registry.soil_moisture_sensor.max_reading_age_s`).
    stale = irrigation_soil_input(_reading(unit="available_pct", age=timedelta(hours=5)), now=_NOW)
    assert stale["usable_pct"] is None
    assert stale["soil_moisture_pct"] == 25.0  # الخامُ يبقى معروضاً
    assert stale["soil_moisture_age_s"] == 18000.0
    assert stale["soil_moisture_freshness"] == "stale"
    assert stale["soil_moisture_used"] is False
    assert stale["soil_moisture_limitations"] == ["soil_moisture_sensor_reading_stale"]

    fresh_aw = irrigation_soil_input(
        _reading(unit="available_pct", age=timedelta(hours=1)), now=_NOW
    )
    assert (fresh_aw["usable_pct"], fresh_aw["soil_moisture_used"]) == (25.0, True)
    assert fresh_aw["soil_moisture_limitations"] == []

    none = irrigation_soil_input(None, now=_NOW)
    assert none["usable_pct"] is None and none["soil_moisture_used"] is False


_DRY_DAYS = [{"et0_mm": 5.0, "precipitation_mm": 0.0}] * 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("unit", "age", "urgency", "used"),
    [
        # VWC 25٪ كانت تُقرأ «ماءً متاحاً ٢٥٪» < ٣٠ ⇒ high. الآن: الاحتياجُ وحدَه (5.8 ⇒ moderate).
        ("vwc_pct", timedelta(minutes=30), "moderate", False),
        # قراءةُ ماءٍ متاح قبل ٥ ساعات (> ٤) كانت تُعامَل قراءةَ الآن ⇒ high. الآن: لا تبلغ المُقرِّر.
        ("available_pct", timedelta(hours=5), "moderate", False),
        # الحالةُ السويّة باقية: ماءٌ متاح طازج ٢٥٪ < ٣٠ ⇒ high.
        ("available_pct", timedelta(minutes=30), "high", True),
    ],
)
async def test_workspace_irrigation_respects_soil_unit_and_age(
    monkeypatch, unit, age, urgency, used
):
    reading = SoilMoistureReading(
        value_pct=25.0,
        recorded_at=datetime.now(UTC) - age,
        unit=unit,
        unit_kind=unit,
    )
    wmod = _patch_workspace(monkeypatch, forecast_days=_DRY_DAYS, soil=reading)
    out = await wmod.field_irrigation_advice_facade("fld_1", user=object())
    assert out["recommended_mm"] == pytest.approx(5.8)
    assert out["urgency"] == urgency
    assert out["soil_moisture_used"] is used
    assert out["soil_moisture_unit_kind"] == unit
    assert out["soil_moisture_pct"] == 25.0
    assert "usable_pct" not in out


def test_the_alert_path_reads_the_same_recent_rain_window():
    """تنبيهُ `low_moisture` يحسب الاحتياجَ نفسَه — فمطرُه الأخير التعريفُ نفسُه لا `current`.

    (كان ``(3.0, 3.0, 6.0)``: مجموعُ اليوم المتوقَّع يُخصَم «أخيراً» — عطلُ مراجعة #1329.)
    """
    from types import SimpleNamespace

    from api.field_context import alert_rain_context

    forecast = [SimpleNamespace(precipitation_mm=mm) for mm in (3.0, 1.0, 2.0)]
    assert alert_rain_context(forecast) == (0.0, 6.0, 6.0)
    gap = [SimpleNamespace(precipitation_mm=mm) for mm in (None, 1.0, 2.0)]
    assert alert_rain_context(gap) == (0.0, None, None)
