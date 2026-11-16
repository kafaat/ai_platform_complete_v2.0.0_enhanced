"""W1-08 (``fields-4``/``crop-5``): ميزات تقدير العائد من الخادم لا من جسم الطلب.

يثبت هذا الملفّ (نقيّاً، بلا قاعدة ولا شبكة):
  • القبول: حقلٌ له مشاهدات آفات ميدانيّة (``scouting_pins``) وتنبيهات إجهاد مائي مخزَّنة + طقسٌ
    جافّ ⇒ عائدٌ أقلّ من المستهدف مع ``evidence_ids`` تسمّي المشاهدات والأحداث وقطعة الطقس.
  • لا آفات من ``events``: لا منتِج لأحداث ``pest.*`` ولا نوع تنبيه آفة في المخطّط.
  • الضابط السلبيّ: سجلّ ريٍّ وحده لا يرصد «صفر آفات، صفر إجهاد» ⇒ لا رقم.
  • NDVI يُرحَّل من تاريخ البذار، ونقطةٌ بلا غيم مقيس لا تُستعمل.
  • يومٌ بهطولٍ مجهول يُبطل سلسلة الطقس (لا صفر مطر).
  • قيمة الطلب تجاوزٌ مُعلَن مع قيمة الخادم التي استبدلها.

الكود في ``api/yield_heuristics.py`` (قسم W1-08). النقطة نفسها على قاعدة حيّة: ``tests_v9/test_yield_server_features_live_pg.py``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

pytestmark = pytest.mark.unit

import api.main  # noqa: E402,F401  (يُحمَّل أوّلاً لكسر الاستيراد الدائريّ)
from api.yield_heuristics import (  # noqa: E402
    CROP_TARGET_YIELDS,
    SOURCE_EVENTS,
    SOURCE_NDVI,
    SOURCE_OVERRIDE,
    SOURCE_SCOUTING,
    SOURCE_UNKNOWN,
    SOURCE_WEATHER,
    SeasonWindow,
    apply_declared_overrides,
    assemble_server_features,
    detect_anomalies,
    estimate_yield,
    ndvi_history_from_points,
    normalize_stored_event,
)

SOW = date(2026, 9, 1)
END = date(2026, 10, 10)
DAYS = (END - SOW).days + 1


def _window(irrigation_type: str | None = "drip") -> SeasonWindow:
    return SeasonWindow(
        season_id="ssn-1",
        crop="wheat",
        sowing_date=SOW,
        end_date=END,
        irrigation_type=irrigation_type,
    )


def _ev(event_id: str, event_type: str, day: int, payload: dict | None = None) -> dict:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "payload": payload or {"field_id": "fld-1"},
        "occurred_at": datetime(2026, 9, 1, 8, tzinfo=UTC) + timedelta(days=day),
    }


def _pin(pin_id: str, category: str, day: int) -> dict:
    """صفّ ``scouting_pins`` بالأعمدة التي يقرؤها ``load_season_and_events``."""
    return {
        "pin_id": pin_id,
        "issue_category": category,
        "issue_code": f"wheat.{category}",
        "severity": "high",
        "created_at": datetime(2026, 9, 1, 10, tzinfo=UTC) + timedelta(days=day),
    }


def _stress_events() -> list[dict]:
    """أحداث بالأنواع التي يُنتجها الخادم فعلاً (نشاط ريّ، تنبيه low_moisture)."""
    return [
        _ev("e-irr-1", "operation.irrigation.completed", 0),
        _ev("e-irr-2", "operation.irrigation.completed", 20),
        _ev("e-moist-1", "alert.created", 15, {"alert_type": "low_moisture"}),
        _ev("e-moist-2", "alert.created", 16, {"alert_type": "low_moisture"}),
        _ev("e-moist-3", "alert.created", 30, {"alert_type": "low_moisture"}),
        _ev("e-noise", "field.updated", 5),
    ]


def _pest_pins() -> list[dict]:
    return [
        _pin("pin-pest-1", "pest", 10),
        _pin("pin-dis-1", "disease", 12),
        _pin("pin-weed", "weed", 13),  # أعشاب ضارّة: ليست آفة/مرضاً
    ]


# ─── القبول ───────────────────────────────────────────────────────────


def test_pest_pins_and_water_stress_events_give_yield_below_target_with_evidence_ids():
    ev = assemble_server_features(
        "fld-1",
        "wheat",
        _window(),
        _stress_events(),
        ndvi_points=[],
        weather_rain_mm=[0.0] * DAYS,
        weather_evidence_id="weather:snap-1",
        pest_pin_rows=_pest_pins(),
    )
    f = ev.features
    assert f.pest_alerts == 2, f"مشاهدتا آفة/مرض (الأعشاب لا تُعدّ)؛ أُعيد {f.pest_alerts}"
    assert f.moisture_stress_events == 3, f"ثلاثة أحداث إجهاد مائي؛ أُعيد {f.moisture_stress_events}"
    assert f.irrigation_count == 2, f.irrigation_count
    # حقلٌ بالتنقيط: سجلّ الريّ لا يرصد أيّام «لا ريّ» ⇒ الجفاف مجهول؛ الآفات والإجهاد يكفيان.
    assert f.drought_streak_days is None, f"جفافٌ مُصطنَع من سجلّ ريّ ناقص؛ أُعيد {f.drought_streak_days}"
    assert f.rain_events == 0, f.rain_events

    est = estimate_yield(f)
    assert est.yield_status == "estimated", est.yield_status
    assert est.estimated_yield_kg_ha < CROP_TARGET_YIELDS["wheat"], (
        f"آفات + إجهاد مائي يجب أن يخفضا العائد تحت المستهدف؛ أُعيد {est.estimated_yield_kg_ha}"
    )
    for eid in ("e-moist-1", "e-moist-2", "e-moist-3", "e-irr-1"):
        assert f"event:{eid}" in ev.evidence_ids, f"{eid} دخل الحساب ولا يظهر في evidence_ids"
    for pid in ("pin-pest-1", "pin-dis-1"):
        assert f"scouting_pin:{pid}" in ev.evidence_ids, f"{pid} دخل الحساب ولا يُستشهد به"
    assert "scouting_pin:pin-weed" not in ev.evidence_ids, "مشاهدة أعشاب ليست دليل آفة"
    assert "event:e-noise" not in ev.evidence_ids, "حدثٌ لم يدخل الحساب لا يُدّعى دليلاً"
    assert "weather:snap-1" in ev.evidence_ids, "قطعة الطقس دخلت الحساب (الأمطار) ولا تظهر دليلاً"
    assert ev.input_sources["pest_alerts"] == SOURCE_SCOUTING, ev.input_sources
    assert ev.input_sources["moisture_stress_events"] == SOURCE_EVENTS, ev.input_sources
    assert ev.input_sources["rain_events"] == SOURCE_WEATHER, ev.input_sources
    assert ev.input_sources["drought_streak_days"] == SOURCE_UNKNOWN, ev.input_sources
    assert ev.window == {
        "season_id": "ssn-1",
        "start": SOW.isoformat(),
        "end": END.isoformat(),
        "irrigation_type": "drip",
    }, ev.window


# ─── الضابط السلبيّ: الغياب ليس صفراً ──────────────────────────────────


def test_irrigation_log_alone_does_not_observe_zero_pests_or_zero_stress():
    events = [
        _ev("e-irr-1", "operation.irrigation.completed", 0),
        _ev("e-irr-2", "operation.irrigation.completed", 5),
    ]
    ev = assemble_server_features(
        "fld-1", "wheat", _window(), events, [], weather_rain_mm=None, weather_evidence_id=None
    )
    f = ev.features
    assert f.pest_alerts is None, f"سجلّ ريّ لا يرصد صفر آفات؛ أُعيد {f.pest_alerts}"
    assert f.moisture_stress_events is None, f"ولا صفر إجهاد؛ أُعيد {f.moisture_stress_events}"
    assert f.drought_streak_days is None, "بلا طقس لا فترة جفاف مُدّعاة"
    assert ev.input_sources["pest_alerts"] == SOURCE_UNKNOWN, ev.input_sources
    est = estimate_yield(f)
    assert est.estimated_yield_kg_ha is None, (
        f"لا دليل على حالة المحصول ⇒ لا رقم؛ أُعيد {est.estimated_yield_kg_ha}"
    )
    assert est.yield_status == "unavailable_insufficient_evidence", est.yield_status
    assert "weather_history_unavailable" in ev.warnings, ev.warnings


def test_no_sown_season_gives_no_server_evidence():
    ev = assemble_server_features(
        "fld-1", "wheat", None, _stress_events(), [], None, None, pest_pin_rows=_pest_pins()
    )
    assert ev.evidence_ids == [], "بلا موسم مزروع لا نافذة ولا أدلّة خادم"
    assert "no_sown_season_no_server_evidence" in ev.warnings, ev.warnings
    assert estimate_yield(ev.features).estimated_yield_kg_ha is None, "لا رقم بلا أدلّة"


def test_irrigated_field_without_irrigation_log_has_unknown_drought():
    ev = assemble_server_features(
        "fld-1",
        "wheat",
        _window("drip"),
        [],
        [],
        [0.0] * DAYS,
        "weather:snap-1",
        pest_pin_rows=[_pin("pin-1", "pest", 3)],
    )
    assert ev.features.drought_streak_days is None, "حقل مرويّ بلا سجلّ ريّ: الجفاف مجهول لا ٤٠ يوماً"
    assert ev.features.rain_events == 0, ev.features.rain_events


def test_one_irrigation_log_on_a_drip_field_does_not_fabricate_drought():
    """مراجعة W1-08: سجلّ ريٍّ واحد كان يجعل كلّ يومٍ بلا سجلّ يوماً جافّاً ⇒ جفاف ٤٩ يوماً حرج."""
    end = date(2026, 10, 20)
    days = (end - SOW).days + 1
    window = SeasonWindow("ssn-1", "wheat", SOW, end, "drip")
    events = [_ev("e-irr-1", "operation.irrigation.completed", 0)]
    ev = assemble_server_features("fld-1", "wheat", window, events, [], [0.0] * days, "weather:w")
    f = ev.features
    assert f.drought_streak_days is None, f"سجلّ ريّ ناقص لا يرصد جفافاً؛ أُعيد {f.drought_streak_days}"
    assert ev.input_sources["drought_streak_days"] == SOURCE_UNKNOWN, ev.input_sources
    assert "drought_unknown_irrigation_not_fully_observed" in ev.warnings, ev.warnings
    est = estimate_yield(f)
    assert est.estimated_yield_kg_ha is None, (
        f"بلا دليل حالة لا رقم؛ أُعيد {est.estimated_yield_kg_ha}"
    )
    anomalies = detect_anomalies(f)
    assert not any(a.type == "drought_streak" for a in anomalies), anomalies


def test_rainfed_season_measures_drought_from_rain_alone():
    rain = [0.0] * DAYS
    rain[10] = 12.0
    ev = assemble_server_features(
        "fld-1", "wheat", _window("rainfed"), [], [], rain, "weather:snap-2"
    )
    assert ev.features.irrigation_count == 0, "بعليّ مُعلَن ⇒ صفر ريّ مرصود"
    assert ev.features.drought_streak_days == DAYS - 11, ev.features.drought_streak_days
    assert ev.features.rain_events == 1, ev.features.rain_events


def test_a_day_with_unknown_precipitation_invalidates_weather_inputs():
    rain: list[float | None] = [0.0] * DAYS
    rain[7] = None
    ev = assemble_server_features(
        "fld-1", "wheat", _window(), _stress_events(), [], rain, "weather:snap-3"
    )
    assert ev.features.rain_events is None, "هطولٌ مجهول ليس صفراً"
    assert ev.features.drought_streak_days is None, "ولا فترة جفاف من سلسلة ناقصة"
    assert "weather:snap-3" not in ev.evidence_ids, "طقسٌ لم يدخل الحساب لا يُدّعى دليلاً"


def test_disease_risk_forecast_is_not_an_observed_pest():
    row = _ev("e-risk", "alert.created", 3, {"alert_type": "disease_risk"})
    assert normalize_stored_event(row) is None, "تنبّؤ خطر مرض ليس رصد آفة"


def test_pest_shaped_events_have_no_producer_and_are_not_pest_evidence():
    """مراجعة W1-08: لا منتِج لأحداث ``pest.*`` ولا لتنبيه آفة؛ قراءتها كانت تدّعي دليلاً
    لا يوجد في الإنتاج. مصدر الآفات الوحيد ``scouting_pins``."""
    from api.alert_models import _ALERT_TYPES

    assert not any("pest" in t for t in _ALERT_TYPES), (
        f"ظهر نوع تنبيه آفة ({_ALERT_TYPES}); أعِد النظر في مصدر الآفات قبل تغيير هذا الاختبار"
    )
    rows = [
        _ev("e-pest-1", "pest.detected", 3),
        _ev("e-dis-1", "disease.detected", 4),
        _ev("e-pest-2", "alert.created", 5, {"alert_type": "pest_detected"}),
        _ev("e-pest-3", "alert.created", 6, {"alert_type": "other", "pest_detected": True}),
    ]
    for row in rows:
        assert normalize_stored_event(row) is None, f"{row['event_type']} ليس دليل آفة: {row}"
    ev = assemble_server_features("fld-1", "wheat", _window(), rows, [], None, None)
    assert ev.features.pest_alerts is None, (
        f"لا مشاهدة ⇒ آفات مجهولة؛ أُعيد {ev.features.pest_alerts}"
    )
    assert ev.input_sources["pest_alerts"] == SOURCE_UNKNOWN, ev.input_sources
    assert ev.evidence_ids == [], f"لا دليل يُدّعى من أحداثٍ بلا منتِج: {ev.evidence_ids}"


def test_pest_pins_outside_the_season_window_are_not_counted():
    pins = [_pin("pin-before", "pest", -3), _pin("pin-after", "pest", DAYS + 2)]
    ev = assemble_server_features(
        "fld-1", "wheat", _window(), [], [], None, None, pest_pin_rows=pins
    )
    assert ev.features.pest_alerts is None, ev.features.pest_alerts
    assert ev.evidence_ids == [], ev.evidence_ids


# ─── يوم التنفيذ لا زمن التسجيل ───────────────────────────────────────


def test_activity_events_are_windowed_on_performed_on_not_recording_time():
    late = _ev(
        "e-irr-late",
        "operation.irrigation.completed",
        DAYS + 3,  # سُجِّل بعد نهاية الموسم
        {"field_id": "fld-1", "performed_on": (END - timedelta(days=2)).isoformat()},
    )
    preplant = _ev(
        "e-fert-pre",
        "operation.fertilizer.applied",
        1,  # سُجِّل داخل الموسم
        {"field_id": "fld-1", "performed_on": (SOW - timedelta(days=5)).isoformat()},
    )
    inside = _ev(
        "e-fert-in",
        "operation.fertilizer.applied",
        4,
        {"field_id": "fld-1", "performed_on": (SOW + timedelta(days=2)).isoformat()},
    )
    ev = assemble_server_features(
        "fld-1", "wheat", _window(), [late, preplant, inside], [], None, None
    )
    assert ev.features.irrigation_count == 1, (
        f"ريٌّ نُفِّذ داخل الموسم وسُجِّل بعده يُعدّ؛ أُعيد {ev.features.irrigation_count}"
    )
    assert ev.features.fertilizer_applications == 1, (
        f"تسميدٌ نُفِّذ قبل البذار لا يُعدّ للموسم؛ أُعيد {ev.features.fertilizer_applications}"
    )
    assert "event:e-irr-late" in ev.evidence_ids, ev.evidence_ids
    assert "event:e-fert-pre" not in ev.evidence_ids, ev.evidence_ids
    mapped = normalize_stored_event(late)
    assert mapped["timestamp"].startswith((END - timedelta(days=2)).isoformat()), (
        f"طابع الحدث يوم التنفيذ لا يوم التسجيل: {mapped['timestamp']}"
    )


def test_malformed_performed_on_falls_back_to_recording_time():
    row = _ev(
        "e-irr-x", "operation.irrigation.completed", 3, {"field_id": "f", "performed_on": "x"}
    )
    mapped = normalize_stored_event(row)
    assert mapped["day"] == SOW + timedelta(days=3), f"قيمة مشوّهة ⇒ زمن التسجيل: {mapped}"


# ─── NDVI من raster ───────────────────────────────────────────────────


def test_ndvi_is_staged_from_sowing_and_unqualified_points_are_dropped():
    points = [
        {"datetime": "2026-09-20T10:00:00Z", "mean": 0.40, "cloud_pct": 5, "scene_id": "S2A_1"},
        {"datetime": "2026-09-25T10:00:00Z", "mean": 0.30, "cloud_pct": 10, "scene_id": "S2A_2"},
        {"datetime": "2026-09-28T10:00:00Z", "mean": 0.90, "cloud_pct": None},
        {"datetime": "2026-09-29T10:00:00Z", "mean": 0.95, "cloud_pct": 80},
        {"datetime": "2026-08-01T10:00:00Z", "mean": 0.99, "cloud_pct": 0},
    ]
    ev = assemble_server_features("fld-1", "wheat", _window(), [], points, None, None)
    assert ev.features.avg_ndvi_growing == pytest.approx(0.35), (
        f"نقطتان مؤهّلتان فقط داخل النافذة؛ أُعيد {ev.features.avg_ndvi_growing}"
    )
    assert ev.input_sources["avg_ndvi_growing"] == SOURCE_NDVI, ev.input_sources
    assert {"raster:ndvi:S2A_1", "raster:ndvi:S2A_2"} <= set(ev.evidence_ids), ev.evidence_ids
    assert "ndvi_points_dropped_unqualified:2" in ev.warnings, ev.warnings
    est = estimate_yield(ev.features)
    assert any("NDVI منخفض" in c for c in est.contributors), est.contributors


def test_malformed_raster_points_are_dropped_not_raised():
    """مراجعة W1-08: ``float(mean)``/``float(cloud)`` غير محميّين كانا يرفعان خارج الواجهة."""
    points = [
        {"datetime": "2026-09-20T10:00:00Z", "mean": "abc", "cloud_pct": 5},
        {"datetime": "2026-09-21T10:00:00Z", "mean": 0.4, "cloud_pct": "cloudy"},
        {"datetime": "2026-09-22T10:00:00Z", "mean": float("nan"), "cloud_pct": 1},
        {"datetime": "2026-09-23T10:00:00Z", "mean": 7.5, "cloud_pct": 1},
        {"datetime": "2026-09-24T10:00:00Z", "mean": 0.5, "cloud_pct": -4},
        {"datetime": "2026-09-25T10:00:00Z", "mean": [0.4], "cloud_pct": 1},
        {"datetime": "2026-09-26T10:00:00Z", "mean": 0.42, "cloud_pct": "3", "scene_id": "ok"},
    ]
    history, ids, warnings = ndvi_history_from_points(points, _window(), "wheat")
    assert [h["ndvi_mean"] for h in history] == [0.42], f"تبقى النقطة الصالحة وحدها: {history}"
    assert ids == ["raster:ndvi:ok"], ids
    assert "ndvi_points_dropped_unqualified:6" in warnings, warnings


# ─── التجاوزات المُعلَنة ──────────────────────────────────────────────


def test_request_values_are_declared_overrides_with_the_server_value_they_replace():
    ev = assemble_server_features(
        "fld-1",
        "wheat",
        _window(),
        _stress_events(),
        [],
        [0.0] * DAYS,
        "weather:snap-1",
        pest_pin_rows=_pest_pins(),
    )
    apply_declared_overrides(ev, {"pest_alerts": 0, "avg_ndvi_growing": 0.7, "crop": "wheat"})
    assert ev.features.pest_alerts == 0, ev.features.pest_alerts
    assert ev.input_sources["pest_alerts"] == SOURCE_OVERRIDE, ev.input_sources
    by_input = {o["input"]: o for o in ev.declared_overrides}
    assert set(by_input) == {"pest_alerts", "avg_ndvi_growing"}, by_input
    assert by_input["pest_alerts"]["server_value"] == 2, by_input
    assert by_input["pest_alerts"]["server_source"] == SOURCE_SCOUTING, by_input
    assert by_input["avg_ndvi_growing"]["server_value"] is None, by_input
    for pid in ("pin-pest-1", "pin-dis-1"):
        assert f"scouting_pin:{pid}" not in ev.evidence_ids, (
            f"مشاهدة {pid} استُبدلت بتجاوزٍ مُعلَن فلم تدخل الحساب؛ لا يُستشهد بها: {ev.evidence_ids}"
        )
    assert "event:e-moist-1" in ev.evidence_ids, "الإجهاد المائي لم يُتجاوَز ويبقى دليلاً"


def test_overriding_every_weather_input_drops_the_weather_citation():
    rain = [0.0] * DAYS
    ev = assemble_server_features(
        "fld-1", "wheat", _window("rainfed"), [], [], rain, "weather:snap-r"
    )
    assert "weather:snap-r" in ev.evidence_ids, ev.evidence_ids
    apply_declared_overrides(ev, {"rain_events": 4, "drought_streak_days": 0})
    assert "weather:snap-r" not in ev.evidence_ids, (
        f"كلّ ما غذّته قطعة الطقس استُبدل؛ لا يُستشهد بها: {ev.evidence_ids}"
    )


def test_mature_only_ndvi_scenes_are_cited_for_the_mature_average():
    points = [
        {"datetime": "2026-10-09T10:00:00Z", "mean": 0.60, "cloud_pct": 5, "scene_id": "S2_M"},
    ]
    window = SeasonWindow("ssn-1", "wheat", date(2026, 5, 1), END, "drip")
    ev = assemble_server_features("fld-1", "wheat", window, [], points, None, None)
    assert ev.features.avg_ndvi_growing is None, ev.features.avg_ndvi_growing
    assert ev.features.avg_ndvi_mature == pytest.approx(0.60), ev.features.avg_ndvi_mature
    assert "raster:ndvi:S2_M" in ev.evidence_ids, (
        f"مشهد MATURE دخل الحساب (الثقة) ولا يُستشهد به: {ev.evidence_ids}"
    )


# ─── التجميع غير المتزامن: نوافذ الشبكة والمحصول ───────────────────────


def test_collect_reads_weather_until_yesterday_and_matches_a_localized_crop(monkeypatch):
    import asyncio

    import api.yield_heuristics as ysf

    calls: dict = {}

    async def ndvi(field_id, tenant_id):
        calls["ndvi"] = (field_id, tenant_id)
        return []

    async def weather(location, start, end, tenant_id):
        calls["weather"] = (location, start, end)
        return [0.0] * ((end - start).days + 1), "weather:snap-c"

    monkeypatch.setattr(ysf, "load_ndvi_points", ndvi)
    monkeypatch.setattr(ysf, "load_weather_rain", weather)
    today = END + timedelta(days=5)
    loaded = ysf.LoadedSeason(today, _window(), _stress_events(), (15.4, 44.3))
    ev = asyncio.run(ysf.collect_server_evidence("fld-1", {"crop": " قمح "}, loaded, "t-1"))
    assert calls["weather"] == ((15.4, 44.3), SOW, END), (
        f"نافذة الطقس = البذار..نهاية الموسم (≤ أمس)؛ أُعيد {calls['weather']}"
    )
    assert calls["ndvi"] == ("fld-1", "t-1"), calls
    assert ev.declared_overrides == [], (
        f"«قمح» هو محصول الموسم نفسه بعد التطبيع؛ ليس تجاوزاً: {ev.declared_overrides}"
    )
    assert ev.features.crop == "wheat", f"محصول الموسم يحكم الحساب؛ أُعيد {ev.features.crop}"


def _stub_network(monkeypatch):
    import api.yield_heuristics as ysf

    async def ndvi(field_id, tenant_id):
        return []

    async def weather(location, start, end, tenant_id):
        return None, None

    monkeypatch.setattr(ysf, "load_ndvi_points", ndvi)
    monkeypatch.setattr(ysf, "load_weather_rain", weather)
    return ysf


def test_declared_crop_conflicting_with_the_season_crop_is_409_not_a_silent_win(monkeypatch):
    import asyncio

    from fastapi import HTTPException

    ysf = _stub_network(monkeypatch)
    loaded = ysf.LoadedSeason(END, _window(), _stress_events(), None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ysf.collect_server_evidence("fld-1", {"crop": "barley"}, loaded, "t-1"))
    assert exc.value.status_code == 409, f"محصولٌ يخالف الموسم ⇒ 409؛ أُعيد {exc.value.status_code}"
    assert exc.value.detail["code"] == "declared_crop_conflicts_with_season_crop", exc.value.detail


def test_declared_crop_without_a_season_crop_is_a_declared_override(monkeypatch):
    import asyncio

    ysf = _stub_network(monkeypatch)
    window = SeasonWindow("ssn-1", None, SOW, END, "drip")
    loaded = ysf.LoadedSeason(END, window, [], None)
    ev = asyncio.run(ysf.collect_server_evidence("fld-1", {"crop": "wheat"}, loaded, "t-1"))
    crop_overrides = [o for o in ev.declared_overrides if o["input"] == "crop"]
    assert crop_overrides == [
        {
            "input": "crop",
            "declared_value": "wheat",
            "server_value": None,
            "server_source": SOURCE_UNKNOWN,
        }
    ], f"بلا محصول موسم يكون المُعلَن تجاوزاً مُعلَناً: {ev.declared_overrides}"
    assert ev.features.crop == "wheat", ev.features.crop


def test_collect_passes_loaded_pest_pins_into_the_estimate(monkeypatch):
    import asyncio

    ysf = _stub_network(monkeypatch)
    loaded = ysf.LoadedSeason(END, _window(), [], None, pest_pin_rows=_pest_pins())
    ev = asyncio.run(ysf.collect_server_evidence("fld-1", {}, loaded, "t-1"))
    assert ev.features.pest_alerts == 2, ev.features.pest_alerts
    assert "scouting_pin:pin-pest-1" in ev.evidence_ids, ev.evidence_ids


def test_truncated_season_events_are_declared_in_warnings(monkeypatch):
    import asyncio

    import api.yield_heuristics as ysf

    async def ndvi(field_id, tenant_id):
        return []

    async def weather(location, start, end, tenant_id):
        return None, None

    monkeypatch.setattr(ysf, "load_ndvi_points", ndvi)
    monkeypatch.setattr(ysf, "load_weather_rain", weather)
    loaded = ysf.LoadedSeason(END, _window(), _stress_events(), None, events_truncated=True)
    ev = asyncio.run(ysf.collect_server_evidence("fld-1", {}, loaded, "t-1"))
    assert f"season_events_truncated_oldest_dropped:{ysf.MAX_SEASON_EVENTS}" in ev.warnings, (
        f"بلوغ سقف الأحداث يُعلَن لا يُسقَط صامتاً: {ev.warnings}"
    )


def test_collect_without_any_known_crop_is_422(monkeypatch):
    import asyncio

    import api.yield_heuristics as ysf
    from fastapi import HTTPException

    loaded = ysf.LoadedSeason(END, None, [], None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ysf.collect_server_evidence("fld-1", {}, loaded, "t-1"))
    assert exc.value.status_code == 422, exc.value.status_code
