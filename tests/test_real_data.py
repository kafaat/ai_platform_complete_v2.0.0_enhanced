"""
SAHOOL v9.0 — tests/test_real_data.py
══════════════════════════════════════
اختبارات التكامل الحقيقي:
  ✅ Open-Meteo API (يختبر الاتصال الفعلي)
  ✅ Hargreaves ET0 (يتحقق من الصحة الرياضية)
  ✅ WOFOST-RUE (يتحقق من منطق النمو)
  ✅ AGB Model (يتحقق من النطاق)
  ✅ Sentinel Hub (إذا توفرت credentials)

تشغيل: pytest tests/test_real_data.py -v
"""

import asyncio
import math
import os
import sys
from datetime import date, timedelta

import pytest

# اختبارات بيانات حقيقيّة تعتمد شبكة خارجيّة (Open-Meteo/WOFOST) — تُشغَّل فقط عند
# REAL_DATA_TESTS=1 كي لا تُحمِّر CI/البيئات بلا إنترنت (فشل بيئيّ لا منطقيّ).
pytestmark = pytest.mark.skipif(
    not os.getenv("REAL_DATA_TESTS"),
    reason="اختبارات بيانات حقيقيّة تتطلّب شبكة — فعّلها بـREAL_DATA_TESTS=1",
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ══════════════════════════════════════════════════════════════
# ١. اختبار Open-Meteo API الحقيقي
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_openmeteo_real():
    """يتصل بـ Open-Meteo ويتحقق من البيانات."""
    from shared.wofost import fetch_weather_real

    lat, lon = 15.05, 45.55  # حقل وادي سبأ
    end = date.today()
    start = end - timedelta(days=7)

    weather = await fetch_weather_real(lat, lon, start, end)

    assert len(weather) >= 5, f"Expected ≥5 days, got {len(weather)}"
    for d in weather:
        assert "date" in d
        assert "tmax" in d
        assert "et0_mm" in d
        assert 10 <= d["tmax"] <= 55, f"Unrealistic tmax: {d['tmax']}"
        assert 0 <= d["tmin"] <= 40, f"Unrealistic tmin: {d['tmin']}"
        assert d["et0_mm"] >= 0, f"Negative ET0: {d['et0_mm']}"

    print(
        f"\n✅ Open-Meteo: {len(weather)} أيام | "
        f"avg_tmax={sum(d['tmax'] for d in weather) / len(weather):.1f}°C | "
        f"total_et0={sum(d['et0_mm'] for d in weather):.1f}mm"
    )


# ══════════════════════════════════════════════════════════════
# ٢. اختبار Hargreaves ET0
# ══════════════════════════════════════════════════════════════
def test_hargreaves_et0():
    """يتحقق من صحة معادلة Hargreaves-Samani (FAO-56)."""
    from shared.wofost import hargreaves_et0

    # قيم مرجعية من FAO-56 Example 17 (اليمن تقريباً)
    # تماز يناير: tmax=24, tmin=11, lat=15°, DOY=15
    et0 = hargreaves_et0(24, 11, 15.0, 15)
    assert 2.0 <= et0 <= 5.0, f"ET0 out of range: {et0}"

    # مايو: حار (tmax=36, tmin=22)
    et0_may = hargreaves_et0(36, 22, 15.0, 135)
    assert et0_may > et0, "ET0 in May should be higher than January"
    assert 5.0 <= et0_may <= 12.0, f"May ET0 unrealistic: {et0_may}"

    print(f"\n✅ Hargreaves ET0: Jan={et0:.2f} May={et0_may:.2f} mm/day")


# ══════════════════════════════════════════════════════════════
# ٣. اختبار WOFOST-RUE كامل
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_wofost_wheat_real():
    """محاكاة WOFOST كاملة للقمح بطقس حقيقي."""
    from shared.wofost import simulate_wofost

    result = await simulate_wofost(
        field_id="field_01",
        crop="قمح صلب",
        soil_type="loam",
        lat=15.05,
        lon=45.55,
        planting_date=date(2026, 1, 15),
        area_ha=23.5,
        irrigation=True,
    )

    assert "error" not in result, f"WOFOST error: {result}"
    assert "simulation" in result
    sim = result["simulation"]

    # التحقق من النطاق الواقعي
    assert 100 <= sim["gdd_accumulated"] <= 2000, f"GDD: {sim['gdd_accumulated']}"
    assert 0.5 <= sim["lai_max"] <= 8.0, f"LAI: {sim['lai_max']}"
    assert 0.5 <= sim["yield_t_ha"] <= 8.0, f"Yield: {sim['yield_t_ha']}"
    assert 1000 <= sim["biomass_kg_ha"] <= 15000, f"Biomass: {sim['biomass_kg_ha']}"
    assert 0 <= sim["progress_pct"] <= 100, f"Progress: {sim['progress_pct']}"

    wb = result["water_balance"]
    assert wb["total_etc_mm"] > 0
    assert wb["water_productivity_kg_m3"] > 0

    print("\n✅ WOFOST القمح (حقيقي):")
    print(
        f"   GDD={sim['gdd_accumulated']:.0f} | LAI={sim['lai_max']:.2f} | "
        f"Yield={sim['yield_t_ha']:.2f} t/ha | Progress={sim['progress_pct']:.0f}%"
    )
    print(
        f"   ETc={wb['total_etc_mm']:.0f}mm | WP={wb['water_productivity_kg_m3']:.2f} kg/m³"
    )
    print(f"   مصدر الطقس: {result['data_source']}")


# ══════════════════════════════════════════════════════════════
# ٤. اختبار جميع المحاصيل
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_all_crops():
    from shared.wofost import simulate_wofost

    FIELDS_TEST = [
        ("field_02", "شعير", "clay_loam", 15.02, 45.58),
        ("field_03", "ذرة صفراء", "sandy_loam", 14.98, 45.52),
        ("field_04", "طماطم", "loam", 14.92, 45.48),
    ]
    for fid, crop, soil, lat, lon in FIELDS_TEST:
        r = await simulate_wofost(
            fid, crop, soil, lat, lon, date(2026, 2, 1), area_ha=20, irrigation=True
        )
        assert "error" not in r, f"{crop}: {r}"
        assert r["simulation"]["yield_t_ha"] > 0, f"{crop}: zero yield"
        print(f"✅ {crop}: {r['simulation']['yield_t_ha']:.2f} t/ha")


# ══════════════════════════════════════════════════════════════
# ٥. اختبار نموذج AGB
# ══════════════════════════════════════════════════════════════
def test_agb_model():
    from random_forest.agb_model import AGBFeatures, get_agb_model

    model = get_agb_model()

    # حقل وادي سبأ (قمح صلب، NDVI=0.72)
    feat = AGBFeatures(
        ndvi=0.72,
        evi=0.61,
        gndvi=0.68,
        savi=0.65,
        vv_backscatter=-12.5,
        vh_backscatter=-18.3,
        area_ha=23.5,
        crop="قمح صلب",
    )
    result = model.predict(feat)

    assert 1.0 <= result["agb_t_ha"] <= 25.0, f"AGB out of range: {result['agb_t_ha']}"
    assert result["yield_t_ha"] > 0
    assert result["agb_t_ha_lower"] < result["agb_t_ha"] < result["agb_t_ha_upper"]
    assert result["confidence_pct"] == 85

    print(
        f"\n✅ AGB model: {result['agb_t_ha']:.2f} t/ha "
        f"[{result['agb_t_ha_lower']:.1f}, {result['agb_t_ha_upper']:.1f}]"
    )
    print(
        f"   Yield: {result['yield_t_ha']:.3f} t/ha | Total: {result['total_yield_t']:.1f} t"
    )
    print(f"   Method: {result['method']}")


# ══════════════════════════════════════════════════════════════
# ٦. اختبار Kc Curve (FAO-56)
# ══════════════════════════════════════════════════════════════
def test_kc_curve():
    from shared.wofost import CROP_PARAMS, get_kc

    p = CROP_PARAMS["قمح صلب"]
    total = p["l_ini"] + p["l_dev"] + p["l_mid"] + p["l_late"]

    kc_ini = get_kc(5, p)
    kc_mid = get_kc(p["l_ini"] + p["l_dev"] + 10, p)
    kc_end = get_kc(total - 5, p)

    assert abs(kc_ini - p["kc_ini"]) < 0.01, f"Kc_ini mismatch: {kc_ini}"
    assert abs(kc_mid - p["kc_mid"]) < 0.05, f"Kc_mid mismatch: {kc_mid}"
    assert kc_mid > kc_ini, "Mid-season Kc should be higher than initial"
    assert kc_end <= kc_mid, "Late-season Kc should decrease"

    print(f"\n✅ FAO-56 Kc curve: ini={kc_ini:.3f} mid={kc_mid:.3f} end={kc_end:.3f}")


# ══════════════════════════════════════════════════════════════
# ٧. اختبار Sentinel Hub (اختياري — يتطلب credentials)
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("SENTINELHUB_CLIENT_ID"),
    reason="SENTINELHUB_CLIENT_ID not set — skipping real API test",
)
async def test_sentinel_hub_real():
    from sentinel_hub.vegetation_real import _fetch_sentinel_hub

    result = await _fetch_sentinel_hub(
        lat=15.05,
        lon=45.55,
        delta=0.05,
        date_from=(date.today() - timedelta(days=30)).isoformat(),
        date_to=date.today().isoformat(),
    )

    assert result is not None, "Sentinel Hub returned None"
    assert "ndvi" in result
    ndvi_mean = result["ndvi"]["mean"]
    assert -1 <= ndvi_mean <= 1, f"NDVI out of range: {ndvi_mean}"

    print(f"\n✅ Sentinel Hub (REAL): NDVI={ndvi_mean:.4f}")


# ══════════════════════════════════════════════════════════════
# تشغيل مباشر
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("SAHOOL v9 — اختبارات البيانات الحقيقية")
    print("=" * 60)

    # اختبارات متزامنة
    test_hargreaves_et0()
    test_agb_model()
    test_kc_curve()

    # اختبارات غير متزامنة
    loop = asyncio.new_event_loop()
    loop.run_until_complete(test_openmeteo_real())
    loop.run_until_complete(test_wofost_wheat_real())
    loop.run_until_complete(test_all_crops())
    loop.close()

    print("\n" + "=" * 60)
    print("✅ كل الاختبارات نجحت — النظام يعمل بالبيانات الحقيقية!")
    print("=" * 60)
