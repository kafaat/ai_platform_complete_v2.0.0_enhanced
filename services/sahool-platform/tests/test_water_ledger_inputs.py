"""مدخلات دفتر الماء اليوميّ — شواهد سلوكيّة على الدوالّ النقيّة، وحارسٌ على التوصيل.

العامل اليوميّ في مسار GATE-01 مجمَّد، فالمنطقُ نُقِل إلى ``api.water_ledger_inputs``
ويُختبَر هنا سلوكيّاً؛ والتوصيلُ في العامل يُقرأ من المصدر (لا يُحمَّل العامل بلا قاعدة).
القيم المرجعيّة: FAO-56 Eq. 47 (الريح) · Fig. 34 (Kc) · Table 22 (p).
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path

import pytest
from api import water_ledger_inputs as wli
from api.water_ledger_auto import CONFIDENCE_AUTO, CONFIDENCE_BOOTSTRAP, compute_daily_ledger_entry

TODAY = date(2026, 6, 1)


# ── الريح: المتوسّط على 10م ⇒ 2م بالمعادلة 47، والقصوى لا تُستعمَل ──


def test_wind_height_conversion_matches_fao56_eq47():
    assert wli.wind_2m_from_height(1.0, 10.0) == pytest.approx(0.748, abs=1e-3)
    assert wli.wind_2m_from_height(2.0, 2.0) == pytest.approx(2.0, abs=1e-2)


def test_mean_wind_is_converted_and_the_daily_maximum_is_never_used():
    inputs = wli.et0_weather_inputs(
        {
            "wind_mean_10m_ms": 4.0,
            "wind_max_ms": 11.0,
            "rh_mean_pct": 35,
            "solar_radiation_mj_m2": 24,
        }
    )
    assert inputs["wind_2m_ms"] == pytest.approx(4.0 * 0.748, abs=1e-2)
    assert inputs["rh_mean_pct"] == 35.0 and inputs["solar_rad_mj_m2"] == 24.0


def test_only_a_maximum_wind_leaves_wind_absent_not_borrowed():
    """القصوى وحدها ⇒ ``None``: يسقط المحرّك إلى Hargreaves معلَناً، لا يُضخَّم ET0."""
    inputs = wli.et0_weather_inputs({"wind_max_ms": 11.0, "rh_mean_pct": 40})
    assert inputs["wind_2m_ms"] is None


@pytest.mark.parametrize("rh", [None, -1, 101, float("nan"), True, "40"])
def test_invalid_humidity_is_absent(rh):
    assert wli.et0_weather_inputs({"rh_mean_pct": rh})["rh_mean_pct"] is None


def test_et0_reference_requires_penman_monteith():
    assert wli.et0_is_reference({"method": "fao56_penman_monteith"}), "PM مرجعٌ في السلسلة"
    assert not wli.et0_is_reference({"method": "hargreaves_fallback"}), "Hargreaves عُدَّ مرجعاً"
    assert not wli.et0_is_reference({}), "منتجٌ لا يُعلِن طريقته عُدَّ مرجعاً"


def test_a_single_et0_product_is_reference_only_when_validated():
    """weather-7: PM بلا ارتفاعٍ أو بمدخلٍ مرفوض يصل ``degraded`` — ليس مرجعاً للدفتر."""
    pm = {"method": "fao56_penman_monteith"}
    assert wli.et0_product_is_reference({**pm, "quality_status": "validated"}), "PM validated"
    assert not wli.et0_product_is_reference({**pm, "quality_status": "degraded"}), (
        "PM degraded (ارتفاعٌ مفقود ⇒ مستوى البحر) عُدَّ مرجعاً"
    )
    assert not wli.et0_product_is_reference(pm), "PM بلا جودةٍ مُعلَنة عُدَّ مرجعاً"
    assert not wli.et0_product_is_reference(
        {"method": "hargreaves_fallback", "quality_status": "degraded"}
    ), "Hargreaves عُدَّ مرجعاً"
    assert not wli.et0_product_is_reference(None), "منتجٌ غائب عُدَّ مرجعاً"


# ── Kc الطوريّ: لا منتصف موسمٍ كلَّ يوم ولا احتياطَ القمح ──


def test_a_maize_seedling_is_not_given_mid_season_kc():
    """بادرةُ الذرة (يوم 10) ⇒ Kc الابتدائيّ 0.30 لا 1.20 (كان العامل يكتب 1.20)."""
    kc = wli.daily_kc("maize", TODAY - timedelta(days=10), TODAY)
    assert kc is not None and kc.kc == pytest.approx(0.30) and kc.stage == "initial"


def test_maize_mid_season_and_late_season_follow_the_crop_card():
    mid = wli.daily_kc("maize", TODAY - timedelta(days=80), TODAY)
    late = wli.daily_kc("maize", TODAY - timedelta(days=139), TODAY)
    assert mid.kc == pytest.approx(1.20) and mid.stage == "mid"
    assert late.stage == "late" and late.kc < mid.kc


@pytest.mark.parametrize(
    "crop,sowing",
    [
        ("not-a-crop", TODAY - timedelta(days=30)),
        ("maize", None),
        ("maize", TODAY + timedelta(days=3)),
    ],
    ids=["unknown-crop", "no-sowing-date", "future-sowing"],
)
def test_unknowable_kc_is_none_never_a_wheat_or_mid_fallback(crop, sowing):
    assert wli.daily_kc(crop, sowing, TODAY) is None


# ── p: FAO-56 Table 22 مُعدَّلاً بـETc ──


def test_depletion_fraction_follows_table22_and_the_etc_adjustment():
    assert wli.depletion_fraction("maize", 5.0) == (0.55, False)
    assert wli.depletion_fraction("maize", 8.0) == (pytest.approx(0.43), False)
    assert wli.depletion_fraction("potato", 5.0) == (0.35, False)


def test_a_crop_without_a_table_value_is_flagged_and_bounds_hold():
    p, is_default = wli.depletion_fraction("not-a-crop", 5.0)
    assert (p, is_default) == (0.5, True)
    assert wli.depletion_fraction("onion", 30.0)[0] == 0.1
    assert wli.depletion_fraction("cotton", 0.0)[0] == 0.8


# ── منطقة الجذور: القانونيّة أوّلاً، واحتياطُ القوام بعلَم ──


class _Profile:
    taw_mm = 140.0
    raw_mm = 77.0
    root_depth_m = 0.9


def _zone(monkeypatch, resolved):
    from api import canonical_root_zone_profile as crz

    async def _fake(conn, **kwargs):
        _fake.kwargs = kwargs
        return resolved

    monkeypatch.setattr(crz, "resolve_canonical_root_zone_profile", _fake)
    crop_kc = wli.daily_kc("maize", TODAY - timedelta(days=60), TODAY)
    zone = asyncio.run(
        wli.ledger_root_zone(
            None,
            tenant_id="t",
            field_id="f",
            season_id="s",
            crop_kc=crop_kc,
            variety=None,
            texture="loam",
            etc_mm_day=5.0,
        )
    )
    return zone, _fake.kwargs


def test_the_canonical_root_zone_is_used_with_the_crop_depletion_fraction(monkeypatch):
    zone, kwargs = _zone(monkeypatch, _Profile())
    assert zone["source"] == "canonical_root_zone"
    assert (zone["taw_mm"], zone["raw_mm"]) == (140.0, 77.0)
    assert zone["root_zone_texture_fallback"] is False
    assert kwargs["raw_fraction"] == 0.55, "p ثابتة 0.5 بدل جدول FAO-56 للمحصول"


def test_a_blocked_root_zone_falls_back_to_texture_with_a_flag(monkeypatch):
    zone, _ = _zone(monkeypatch, {"status": "blocked", "reason": "no_soil_profile"})
    assert zone["root_zone_texture_fallback"] is True
    assert zone["source"] == "texture_table_fallback:no_soil_profile"
    assert zone["raw_mm"] == pytest.approx(zone["taw_mm"] * 0.55, abs=0.05)


# ── الأعلام تدخل القيد وتُخفّض الثقة ──


def _entry(**flags):
    return compute_daily_ledger_entry(
        prev_depletion_mm=20.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=6.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=5.0,
        **flags,
    )


def test_a_degraded_et0_or_a_texture_fallback_lowers_confidence():
    assert _entry()["confidence"] == CONFIDENCE_AUTO
    for flag in ("et0_reference_unavailable", "root_zone_texture_fallback"):
        entry = _entry(**{flag: True})
        assert flag in entry["notes"] and entry["confidence"] == CONFIDENCE_BOOTSTRAP


def test_a_default_depletion_fraction_is_declared_without_touching_depletion_confidence():
    entry = _entry(depletion_fraction_default=True)
    assert "depletion_fraction_default" in entry["notes"]
    assert entry["confidence"] == CONFIDENCE_AUTO


# ── التوصيل في العامل المجمَّد (مقروءٌ من المصدر) ──


def test_the_frozen_worker_is_wired_to_the_measured_inputs():
    src = (Path(__file__).parents[1] / "api" / "phase_runtime_workers.py").read_text(
        encoding="utf-8"
    )
    body = src[src.index("async def run_water_ledger_once") : src.index("async def loop_worker")]
    for gone in ('"mid",', "KC_BY_CROP_STAGE", 'day0.get("wind_max_ms")', 'sw["raw_fraction"]'):
        assert gone not in body, f"بقي في العامل: {gone}"
    for wired in (
        "daily_kc(",
        "**et0_weather_inputs(day0)",
        "ledger_root_zone(",
        "et0_reference_unavailable=not et0_product_is_reference(et0)",
        "root_zone_texture_fallback=",
        "crop_kc.stage",
    ):
        assert wired in body, f"غير موصول في العامل: {wired}"


# ── W0-10 / weather-7: الارتفاع · المرجع · مصدر المطر ──


def _weather_et0(monkeypatch):
    import importlib.util

    owner = Path(__file__).resolve().parents[2] / "weather-service"
    monkeypatch.syspath_prepend(str(owner))  # et0.py يستورد vapor_pressure من مجلّده
    path = owner / "et0.py"
    spec = importlib.util.spec_from_file_location("owner_et0_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fao56_pm(*, t_max, t_min, rs, rh, u2, lat_deg, doy, z):
    """FAO-56 Penman-Monteith (Eq. 6) مكتوباً هنا مستقلاً عن المحرّك — شاهدٌ لا نسخة."""
    import math

    p_kpa = 101.3 * ((293.0 - 0.0065 * z) / 293.0) ** 5.26  # Eq. 7
    gamma = 0.665e-3 * p_kpa  # Eq. 8
    t_mean = (t_max + t_min) / 2.0

    def e0(t):
        return 0.6108 * math.exp(17.27 * t / (t + 237.3))  # Eq. 11

    es = (e0(t_max) + e0(t_min)) / 2.0
    ea = rh / 100.0 * es  # Eq. 19 (RH mean)
    delta = 4098.0 * e0(t_mean) / (t_mean + 237.3) ** 2  # Eq. 13
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    dec = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    ws = math.acos(-math.tan(phi) * math.tan(dec))
    ra = (
        24
        * 60
        / math.pi
        * 0.0820
        * dr
        * (ws * math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.sin(ws))
    )  # Eq. 21
    rso = (0.75 + 2e-5 * z) * ra  # Eq. 37
    rnl = (
        4.903e-9
        * ((t_max + 273.16) ** 4 + (t_min + 273.16) ** 4)
        / 2
        * (0.34 - 0.14 * math.sqrt(ea))
        * (1.35 * min(1.0, rs / rso) - 0.35)
    )  # Eq. 39
    rn = 0.77 * rs - rnl
    num = 0.408 * delta * rn + gamma * 900 / (t_mean + 273) * u2 * (es - ea)
    return num / (delta + gamma * (1 + 0.34 * u2))


_HIGHLAND_DAY = {
    "t_max_c": 27.0,
    "t_min_c": 11.0,
    "solar_rad_mj_m2": 24.0,
    "rh_mean_pct": 20.0,
    "wind_2m_ms": 4.0,
    "lat_deg": 15.35,
    "day_of_year": 150,
}


def test_a_2300m_field_gets_the_fao56_elevation_effect_not_sea_level(monkeypatch):
    """حقلٌ عند 2300م: ضغطٌ ~76.9 كيلوباسكال (Eq. 7) لا 101.3، وET0 يفرق بالمقدار المتوقّع."""
    et0 = _weather_et0(monkeypatch)
    high = et0.compute_et0(**_HIGHLAND_DAY, elevation_m=2300.0)
    sea = et0.compute_et0(**_HIGHLAND_DAY, elevation_m=0.0)
    unpassed = et0.compute_et0(**_HIGHLAND_DAY)  # ما كان العامل يرسله: بلا ارتفاع
    kw = {
        "t_max": 27.0,
        "t_min": 11.0,
        "rs": 24.0,
        "rh": 20.0,
        "u2": 4.0,
        "lat_deg": 15.35,
        "doy": 150,
    }
    expected_high = _fao56_pm(**kw, z=2300.0)
    expected_sea = _fao56_pm(**kw, z=0.0)
    assert high["et0_mm"] == pytest.approx(expected_high, abs=2e-3), "PM عند 2300م ≠ FAO-56"
    assert high["et0_mm"] - sea["et0_mm"] == pytest.approx(
        expected_high - expected_sea, abs=3e-3
    ), "فرق الارتفاع لا يطابق FAO-56 Eq. 7"
    # يومٌ جافّ عاصف في المرتفعات: ~0.25 مم/يوم (~3%) — يتراكم في الدفتر يوماً بعد يوم.
    assert abs(expected_high - expected_sea) > 0.2, "المثال لا يُميّز الارتفاع (شاهدٌ ضعيف)"
    assert high["quality_status"] == "validated", "PM بارتفاعٍ معلوم يجب أن يكون validated"
    # ارتفاعٌ لا يُمرَّر = مستوى البحر بجودةٍ متدهورة — وهذا ليس مرجعاً للدفتر.
    assert unpassed["et0_mm"] == sea["et0_mm"], "بلا ارتفاع يحسب المحرّك عند مستوى البحر"
    assert unpassed["quality_status"] == "degraded", "بلا ارتفاع يجب أن يُعلَن degraded"
    assert wli.et0_product_is_reference(high), "PM validated عند 2300م مرجع"
    assert not wli.et0_product_is_reference(unpassed), "PM عند مستوى البحر بلا ارتفاع عُدَّ مرجعاً"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, None), (float("nan"), None), ("2300", None), (True, None), (2300, 2300.0)],
)
def test_field_elevation_is_taken_as_recorded_or_absent(raw, expected):
    assert wli.field_elevation_m(raw) == expected, f"ارتفاع {raw!r}"


def test_field_elevation_reads_postgres_numeric():
    from decimal import Decimal

    assert wli.field_elevation_m(Decimal("2300.0")) == 2300.0, "NUMERIC(7,1) يصل Decimal"


def test_observed_rain_is_matched_by_date_and_absence_stays_absent():
    archive = {
        "days": [
            {"date": "2026-05-30", "precipitation_mm": 9.0},
            {"date": "2026-05-31", "precipitation_mm": 0.0},
        ]
    }
    yesterday = TODAY - timedelta(days=1)
    assert wli.observed_rain_for_date(archive, yesterday) == 0.0, "يومٌ جافّ مرصود = 0"
    assert wli.observed_rain_for_date(archive, TODAY) is None, "يومٌ غائب ليس صفراً"
    missing = {"days": [{"date": "2026-05-31", "precipitation_mm": None}]}
    assert wli.observed_rain_for_date(missing, yesterday) is None, "هطولٌ مفقود ليس صفراً"
    broken = {"days": [{"date": "2026-05-31", "precipitation_mm": -1.0}]}
    assert wli.observed_rain_for_date(broken, yesterday) is None, "هطولٌ سالب قُبِل"
    assert wli.observed_rain_for_date(None, yesterday) is None, "أرشيفٌ غائب قُرِئ"


def _prev(**over):
    row = {
        "ledger_date": TODAY - timedelta(days=1),
        "created_by": "water-balance-auto",
        "rain_source": "forecast",
        "decision": "auto:irrigation_unobserved",
        "depletion_mm": 18.0,
        "etc_mm": 6.0,
        "irrigation_mm": 0.0,
        "rain_mm": 10.0,
        "taw_mm": 120.0,
        "raw_mm": 60.0,
    }
    row.update(over)
    return row


AUTO = "water-balance-auto"


def _day(k: int) -> date:
    return TODAY - timedelta(days=k)


def test_the_window_outlasts_the_archive_lag():
    from api.season_simulation import _ERA5_LAG_DAYS

    assert wli.RAIN_RECONCILE_WINDOW_DAYS > _ERA5_LAG_DAYS, (
        "نافذة إعادة تسجيل المطر لا تتجاوز تأخّر أرشيف ERA5: لن يُرصَد مطرٌ أبداً"
    )


def test_the_archive_is_asked_from_the_oldest_rebuildable_forecast_row_in_the_window():
    rows = [
        _prev(ledger_date=_day(12), rain_source="forecast"),  # خارج النافذة
        _prev(ledger_date=_day(6), created_by="farmer-1"),  # يدويّ
        _prev(ledger_date=_day(5), taw_mm=None),  # بلا TAW مخزَّن (قبل v279)
        _prev(ledger_date=_day(4), decision="auto:missing_days_consumption_estimated"),
        _prev(ledger_date=_day(3)),
        _prev(ledger_date=_day(1)),
    ]
    assert wli.rain_reconcile_start(rows, TODAY, AUTO) == _day(3), (
        "أقدمُ قيدٍ مؤهَّل في النافذة لم يُختَر بدايةً لطلب الأرشيف"
    )
    observed_only = [_prev(ledger_date=_day(k), rain_source="observed") for k in (3, 2, 1)]
    assert wli.rain_reconcile_start(observed_only, TODAY, AUTO) is None, (
        "لا قيدَ متوقَّعاً ⇒ لا نداءَ للأرشيف"
    )
    for over, why in (
        ({"rain_source": None}, "قيدٌ بلا نَسَب"),
        ({"decision": "measured_as_applied"}, "ليس قيد العامل"),
        ({"etc_mm": None}, "ETc مفقود"),
        ({"raw_mm": 130.0}, "RAW فوق TAW"),
    ):
        assert wli.rain_reconcile_start([_prev(**over)], TODAY, AUTO) is None, why


def test_a_row_the_archive_fills_days_later_is_still_re_recorded():
    """المراجعة: الأرشيف يتأخّر ~5 أيّام؛ قيدٌ عمره خمسة أيّام يجب أن يُرصَد حين يمتلئ."""
    from api.water_balance import _effective_rain

    anchor = _prev(ledger_date=_day(6), rain_source="observed", depletion_mm=20.0)
    lagged = _prev(
        ledger_date=_day(5),
        depletion_mm=round(20.0 + 6.0 - _effective_rain(10.0), 2),
    )
    later = [
        _prev(
            ledger_date=_day(k),
            rain_mm=0.0,
            depletion_mm=round(lagged["depletion_mm"] + 6.0 * (5 - k), 2),
        )
        for k in (4, 3, 2, 1)
    ]
    rows = [anchor, lagged, *later]
    # اليومُ السابقُ وحده بلا رصد (تأخّر): لا شيء يُعاد تسجيله إلّا ما رُصِد.
    updates, carry = wli.rebuild_rain_chain(rows, {_day(5): 0.0}, TODAY, AUTO)
    assert [u["ledger_date"] for u in updates] == [_day(k) for k in (5, 4, 3, 2, 1)], (
        "السلسلة بعد اليوم المرصود لم يُعَد بناؤها حتّى الأمس"
    )
    assert updates[0]["rain_source"] == "observed" and updates[0]["rain_mm"] == 0.0, (
        "المطر المتوقَّع قبل خمسة أيّام لم يُستبدَل بالمرصود"
    )
    assert updates[0]["depletion_mm"] == 26.0, "استنزافُ اليوم المرصود لم يُبنَ من مرساته"
    assert all(u["rain_source"] == "forecast" for u in updates[1:]), (
        "قيدٌ لم يُرصَد بعد صار مرصوداً بلا أرشيف"
    )
    assert [u["depletion_mm"] for u in updates[1:]] == [32.0, 38.0, 44.0, 50.0], (
        "الاستنزاف لم ينتقل في السلسلة من اليوم المرصود"
    )
    assert carry == 50.0, "بدايةُ اليوم لم تُؤخذ من الأمس المُعاد بناؤه"
    assert updates[0]["expected_rain_source"] == "forecast", "شرطُ UPDATE لا يحمل المصدر السابق"
    assert updates[1]["expected_depletion_mm"] == later[0]["depletion_mm"], (
        "شرطُ UPDATE لا يحمل الاستنزاف السابق"
    )


def test_the_chain_stops_at_a_manual_row_a_gap_or_the_window_edge():
    anchor = _prev(ledger_date=_day(4), rain_source="observed", depletion_mm=20.0)
    fixed = _prev(ledger_date=_day(3))
    manual = _prev(ledger_date=_day(2), created_by="farmer-1", depletion_mm=5.0)
    after = _prev(ledger_date=_day(1), rain_source="observed", depletion_mm=11.0)
    updates, carry = wli.rebuild_rain_chain(
        [anchor, fixed, manual, after], {_day(3): 0.0}, TODAY, AUTO
    )
    assert [u["ledger_date"] for u in updates] == [_day(3)], "قيدٌ يدويّ أو ما بعده أُعيد بناؤه"
    assert carry is None, "بدايةُ اليوم أُخذت من سلسلةٍ انقطعت عند قيدٍ يدويّ"

    gap = [anchor, _prev(ledger_date=_day(2), rain_source="observed")]
    assert wli.rebuild_rain_chain(gap, {}, TODAY, AUTO) == ([], None), "فجوةٌ لا تُعبَر"
    lone = [_prev(ledger_date=_day(3))]  # لا مرساة ولا تهيئة ⇒ لا بداية
    assert wli.rebuild_rain_chain(lone, {_day(3): 0.0}, TODAY, AUTO) == ([], None), (
        "بدايةٌ مفقودة قُرِئت صفراً"
    )
    edge = [
        _prev(ledger_date=_day(12), rain_source="observed"),
        _prev(ledger_date=_day(11)),
    ]
    assert wli.rebuild_rain_chain(edge, {_day(11): 0.0}, TODAY, AUTO) == ([], None), (
        "قيدٌ خارج النافذة أُعيد تسجيله"
    )


def test_the_row_s_own_taw_is_used_not_today_s():
    """المراجعة: TAW المخزَّن مع القيد لا TAW اليوم (نسيجٌ تغيّر بين الليلتين)."""
    anchor = _prev(ledger_date=_day(2), rain_source="observed", depletion_mm=38.0)
    row = _prev(ledger_date=_day(1), taw_mm=40.0, raw_mm=20.0)
    updates, _ = wli.rebuild_rain_chain([anchor, row], {_day(1): 0.0}, TODAY, AUTO)
    assert updates[0]["depletion_mm"] == 40.0, "القصّ لم يتمّ بـTAW القيد نفسه"
    assert "depletion_capped_at_taw" in updates[0]["decision"], "القصّ لم يُعلَن"


def test_observed_rain_by_date_skips_absent_and_malformed_days():
    archive = {
        "days": [
            {"date": "2026-05-29", "precipitation_mm": 3.5},
            {"date": "2026-05-30", "precipitation_mm": None},
            {"date": "not-a-date", "precipitation_mm": 1.0},
            "junk",
        ]
    }
    assert wli.observed_rain_by_date(archive) == {date(2026, 5, 29): 3.5}, (
        "يومٌ غائب أو تالف قُرِئ رصداً"
    )


def test_forecast_rain_is_replaced_by_the_observed_and_depletion_rebuilt():
    from api.water_balance import _effective_rain

    fixed = wli.reconcile_forecast_rain(
        _prev(), start_depletion_mm=20.0, observed_rain_mm=2.0, taw_mm=120.0, raw_mm=60.0
    )
    assert fixed["rain_source"] == "observed", "المصدر لم يصِر مرصوداً"
    assert fixed["rain_mm"] == 2.0, "المطر المرصود لم يحلّ محلّ المتوقَّع"
    expected = round(20.0 + 6.0 - _effective_rain(2.0) - 0.0, 2)
    assert fixed["depletion_mm"] == expected, "الاستنزاف لم يُبنَ من بداية اليوم بالمطر المرصود"
    # المتوقَّع (10م) كان يُنقِص الاستنزافَ بماءٍ لم يهطل.
    assert fixed["depletion_mm"] > round(20.0 + 6.0 - _effective_rain(10.0), 2), (
        "مطرٌ متوقَّع أكبر من المرصود يجب أن يُخفي استنزافاً"
    )
    assert fixed["decision"] == "auto:irrigation_unobserved", "أعلام الريّ يجب أن تبقى"


def test_reconciliation_drops_the_assumed_zero_flag_and_recaps():
    prev = _prev(decision="auto:precipitation_assumed_zero", rain_mm=0.0)
    fixed = wli.reconcile_forecast_rain(
        prev, start_depletion_mm=115.0, observed_rain_mm=0.0, taw_mm=120.0, raw_mm=60.0
    )
    assert "precipitation_assumed_zero" not in fixed["decision"], "علَمُ مطرٍ مفترَض بقي"
    assert fixed["depletion_mm"] == 120.0 and "depletion_capped_at_taw" in fixed["decision"], (
        "استنزافٌ فوق TAW يُقَصّ ويُعلَن"
    )
    assert fixed["confidence"] == CONFIDENCE_AUTO, "الثقة لم تُشتقَّ من الأعلام الباقية"


def test_a_bootstrap_day_restarts_at_field_capacity_and_a_lost_start_is_not_invented():
    boot = _prev(decision="auto:bootstrap_assumed_field_capacity")
    fixed = wli.reconcile_forecast_rain(
        boot, start_depletion_mm=None, observed_rain_mm=0.0, taw_mm=120.0, raw_mm=60.0
    )
    assert fixed["depletion_mm"] == 6.0, "التهيئة المعلنة تبدأ من Dr=0"
    assert fixed["confidence"] == CONFIDENCE_BOOTSTRAP, "يوم التهيئة يبقى بثقة التهيئة"
    lost = wli.reconcile_forecast_rain(
        _prev(), start_depletion_mm=None, observed_rain_mm=0.0, taw_mm=120.0, raw_mm=60.0
    )
    assert lost is None, "بدايةٌ مفقودة في غير التهيئة قُرِئت صفراً"


def test_the_frozen_worker_passes_elevation_and_records_provenance():
    src = (Path(__file__).parents[1] / "api" / "phase_runtime_workers.py").read_text(
        encoding="utf-8"
    )
    body = src[src.index("async def run_water_ledger_once") : src.index("async def loop_worker")]
    for wired in (
        "f.elevation_m",
        'field_elevation_m(row["elevation_m"])',
        '"skipped": "field_elevation_missing"',
        "elevation_m=elevation_m,",
        "et0_method, et0_quality,",
        "weather_snapshot_id, rain_source,",
        'et0.get("quality_status")',
        "RAIN_SOURCE_FORECAST,",
        "rain_reconcile_start(window_rows, today, AUTO_CREATED_BY)",
        "rebuild_rain_chain(",
        "RAIN_RECONCILE_WINDOW_DAYS + 1",
        'zone["taw_mm"],',
        "prev_depletion_mm=prev_depletion,",
    ):
        assert wired in body, f"غير موصول في العامل: {wired}"
