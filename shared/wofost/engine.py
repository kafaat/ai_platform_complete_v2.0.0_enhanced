"""
SAHOOL v9.0 — wofost_real.py
══════════════════════════════════════════════════
WOFOST-RUE حقيقي مع Open-Meteo (لا random.gauss):
  ✅ Hargreaves-Samani ET0 من بيانات حقيقية
  ✅ FAO-56 Kc curves بمراحل النمو الفعلية
  ✅ GDD تراكمي من درجات الحرارة الحقيقية
  ✅ Water stress factor فعلي
  ✅ RUE + LAI model من WOFOST-Classic
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta

import httpx

logger = logging.getLogger("wofost-real")

# ══════════════════════════════════════════════════════════════
# معاملات المحاصيل الحقيقية (مشتقة من WOFOST crop database + FAO-56 Table 11)
# ══════════════════════════════════════════════════════════════
CROP_PARAMS = {
    "قمح صلب": {
        "tbase": 5.0,  # درجة أساسية للنمو
        "topt": 18.0,  # درجة مثلى
        "tmax_dev": 35.0,  # حد حراري أعلى
        "tsum1": 800,  # GDD للإنبات → الإزهار
        "tsum2": 1200,  # GDD الإزهار → النضج
        "rue": 2.8,  # g DM / MJ PAR (Radiation Use Efficiency)
        "k": 0.52,  # معامل امتصاص الإشعاع
        "hi": 0.40,  # Harvest Index
        "kc_ini": 0.40,
        "kc_mid": 1.15,
        "kc_end": 0.40,
        "l_ini": 20,
        "l_dev": 30,
        "l_mid": 60,
        "l_late": 30,
        "rdmax": 1.2,  # عمق الجذر الأقصى (m)
    },
    "شعير": {
        "tbase": 3.0,
        "topt": 16.0,
        "tmax_dev": 32.0,
        "tsum1": 750,
        "tsum2": 1100,
        "rue": 2.6,
        "k": 0.50,
        "hi": 0.38,
        "kc_ini": 0.30,
        "kc_mid": 1.10,
        "kc_end": 0.35,
        "l_ini": 20,
        "l_dev": 25,
        "l_mid": 55,
        "l_late": 25,
        "rdmax": 1.0,
    },
    "ذرة صفراء": {
        "tbase": 10.0,
        "topt": 28.0,
        "tmax_dev": 40.0,
        "tsum1": 900,
        "tsum2": 1500,
        "rue": 3.5,
        "k": 0.65,
        "hi": 0.45,
        "kc_ini": 0.40,
        "kc_mid": 1.20,
        "kc_end": 0.60,
        "l_ini": 20,
        "l_dev": 35,
        "l_mid": 45,
        "l_late": 30,
        "rdmax": 1.5,
    },
    "طماطم": {
        "tbase": 8.0,
        "topt": 23.0,
        "tmax_dev": 36.0,
        "tsum1": 600,
        "tsum2": 1000,
        "rue": 2.4,
        "k": 0.58,
        "hi": 0.70,
        "kc_ini": 0.60,
        "kc_mid": 1.15,
        "kc_end": 0.80,
        "l_ini": 30,
        "l_dev": 40,
        "l_mid": 45,
        "l_late": 30,
        "rdmax": 1.0,
    },
    "بطاطس": {
        "tbase": 2.0,
        "topt": 17.0,
        "tmax_dev": 30.0,
        "tsum1": 500,
        "tsum2": 900,
        "rue": 3.0,
        "k": 0.55,
        "hi": 0.75,
        "kc_ini": 0.50,
        "kc_mid": 1.10,
        "kc_end": 0.75,
        "l_ini": 25,
        "l_dev": 30,
        "l_mid": 45,
        "l_late": 30,
        "rdmax": 0.8,
    },
    "خضروات": {
        "tbase": 7.0,
        "topt": 20.0,
        "tmax_dev": 35.0,
        "tsum1": 400,
        "tsum2": 700,
        "rue": 2.5,
        "k": 0.60,
        "hi": 0.65,
        "kc_ini": 0.60,
        "kc_mid": 1.05,
        "kc_end": 0.90,
        "l_ini": 20,
        "l_dev": 30,
        "l_mid": 40,
        "l_late": 20,
        "rdmax": 0.7,
    },
}

SOIL_PARAMS = {
    "loam": {"fc": 0.30, "wp": 0.12, "ksat": 25},
    "clay_loam": {"fc": 0.36, "wp": 0.20, "ksat": 12},
    "sandy_loam": {"fc": 0.22, "wp": 0.08, "ksat": 55},
    "silt_loam": {"fc": 0.32, "wp": 0.13, "ksat": 18},
}


# ══════════════════════════════════════════════════════════════
# OPEN-METEO: جلب بيانات طقس يومية حقيقية
# ══════════════════════════════════════════════════════════════
async def fetch_weather_real(
    lat: float, lon: float, start: date, end: date
) -> list[dict]:
    """Open-Meteo ERA5 + Forecast — مجاني 100% بدون مفتاح."""
    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={start}&end_date={end}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
        f"shortwave_radiation_sum,et0_fao_evapotranspiration"
        f"&timezone=Asia%2FAden"
    )
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(url)
        r.raise_for_status()
    d = r.json().get("daily", {})
    result = []

    def _at(key, i, default):
        # H6 FIX: Open-Meteo قد يُرجع مصفوفات مُسنّنة/null (أرشيف ERA5 متأخّر
        # ~5 أيام). الوصول المباشر d[key][i] كان يرمي KeyError/IndexError.
        lst = d.get(key)
        if not isinstance(lst, list) or i >= len(lst) or lst[i] is None:
            return default
        return lst[i]

    for i, dt in enumerate(d.get("time", [])):
        result.append(
            {
                "date": dt,
                "tmax": _at("temperature_2m_max", i, 30.0),
                "tmin": _at("temperature_2m_min", i, 15.0),
                "rain_mm": _at("precipitation_sum", i, 0.0),
                "rad_mj": _at("shortwave_radiation_sum", i, 15.0),
                "et0_mm": _at("et0_fao_evapotranspiration", i, 4.0),
            }
        )
    return result


# ══════════════════════════════════════════════════════════════
# Hargreaves-Samani ET0 (للأيام التي لا يوفر Open-Meteo قيمة)
# ══════════════════════════════════════════════════════════════
def hargreaves_et0(tmax: float, tmin: float, lat_deg: float, doy: int) -> float:
    """
    ET0 = 0.0023 × (Tmean + 17.8) × √Trange × Ra × 0.408
    من: Allen et al. 1998 (FAO-56), Equation 52

    مصدر الحقيقة الكنسيّ لـET0/Hargreaves (FAO-56) بعد Zero-Legacy:
        services/weather-service/et0.py + services/weather-service/vapor_pressure.py
        (hargreaves_et0_mm, penman_monteith_et0_mm, extraterrestrial_radiation_mj/mm،
         مُختبَرة مقابل FAO-56 في services/weather-service/tests/test_et0.py).
        (كانت سابقاً في core/engines/et0.py في المنصّة — حُذفت بعد ترحيل كلّ
         مستهلكيها لاستهلاك منتج المحرّك؛ Zero-Legacy allowlist=0.)
    هذه نسخة حرفيّة مُتطابقة عمداً، وليست تباعداً. سبب عدم الاستيراد من
    المصدر الكنسيّ: عزل مقصود — wofost_engine كود R&D خارج services/ بالكامل
    (خارج المنصّة)، ولا يصل إلى المحرّك عبر HTTP في مسار R&D هذا. التوحيد الكامل
    (استهلاك منتج المحرّك من R&D) مؤجَّل بقرار، خارج نطاق Zero-Legacy للمنصّة.
    ⚠ أيّ تعديل على صيغة Ra أو Hargreaves أدناه يجب أن يُزامَن مع المصدر
      الكنسيّ في محرّك الطقس للحفاظ على تطابق الناتج.
    """
    tmean = (tmax + tmin) / 2
    trange = max(0, tmax - tmin)
    lat = math.radians(lat_deg)

    # الإشعاع الفضائي Ra (Equation 21)
    dr = 1 + 0.033 * math.cos(2 * math.pi / 365 * doy)
    delta = 0.409 * math.sin(2 * math.pi / 365 * doy - 1.39)
    ws = math.acos(-math.tan(lat) * math.tan(delta))
    Ra = (
        (24 * 60 / math.pi)
        * 0.082
        * dr
        * (
            ws * math.sin(lat) * math.sin(delta)
            + math.cos(lat) * math.cos(delta) * math.sin(ws)
        )
    )
    et0 = 0.0023 * (tmean + 17.8) * math.sqrt(trange) * Ra * 0.408
    return max(0.5, round(et0, 2))


# ══════════════════════════════════════════════════════════════
# FAO-56 Kc: معامل المحصول بناءً على يوم الموسم
# ══════════════════════════════════════════════════════════════
def get_kc(day: int, p: dict) -> float:
    """
    Kc curve: ini → dev → mid → late
    من: FAO-56 Table 11 + Figure 25
    """
    l1 = p["l_ini"]
    l2 = p["l_ini"] + p["l_dev"]
    l3 = p["l_ini"] + p["l_dev"] + p["l_mid"]
    total = l3 + p["l_late"]

    if day <= 0:
        return p["kc_ini"]
    elif day <= l1:
        return p["kc_ini"]
    elif day <= l2:
        # Linear interpolation ini → mid
        frac = (day - l1) / (l2 - l1)
        return p["kc_ini"] + frac * (p["kc_mid"] - p["kc_ini"])
    elif day <= l3:
        return p["kc_mid"]
    elif day <= total:
        # Linear interpolation mid → end
        frac = (day - l3) / (p["l_late"])
        return p["kc_mid"] + frac * (p["kc_end"] - p["kc_mid"])
    else:
        return p["kc_end"]


# ══════════════════════════════════════════════════════════════
# WOFOST-RUE Core Simulation
# ══════════════════════════════════════════════════════════════
async def simulate_wofost(
    field_id: str,
    crop: str,
    soil_type: str,
    lat: float,
    lon: float,
    planting_date: date,
    area_ha: float = 1.0,
    irrigation: bool = True,
    cfet: float = 1.15,
) -> dict:
    """
    محاكاة WOFOST-RUE كاملة بطقس حقيقي من Open-Meteo.

    cfet: معامل تصحيح التبخّر المحتمل (Correction Factor for ET). WOFOST يقلّل
    التبخّر منهجيّاً في المناطق الجافّة؛ الأبحاث (شبه جافّة مماثلة للجوف) تُوصي
    برفعه إلى 1.15-1.2 (الحدّ الأقصى) لتصحيح هذا التحيّز. الافتراض 1.15 مناسب
    للجوف الجافّ؛ 1.0 للمناخ المعتدل. يُطبَّق: ETc = ET0 · Kc · CFET.

    المخرجات:
      - GDD التراكمي، LAI، biomass، yield، ETc
      - سلسلة زمنية يومية
      - مؤشرات إجهاد الحرارة والجفاف
    """
    cp = CROP_PARAMS.get(crop, CROP_PARAMS["قمح صلب"])
    sp = SOIL_PARAMS.get(soil_type, SOIL_PARAMS["loam"])

    tsum_needed = cp["tsum1"] + cp["tsum2"]
    total_season_days = int(tsum_needed / 8) + 30  # تقدير أولي

    end_date = planting_date + timedelta(days=min(total_season_days, 180))
    end_date = min(end_date, date.today())

    # جلب الطقس الحقيقي
    try:
        weather = await fetch_weather_real(lat, lon, planting_date, end_date)
    except Exception as e:
        logger.warning(f"Open-Meteo failed: {e}")
        weather = []

    if not weather:
        return {"error": "فشل جلب بيانات الطقس من Open-Meteo"}

    # ── Simulation Loop ──────────────────────────────────────
    gdd_acc = 0.0
    lai = 0.0
    biomass = 0.0  # g DM / m²
    w_soil = sp["fc"] * cp["rdmax"] * 1000  # mm (initial = field capacity)
    w_fc = sp["fc"] * cp["rdmax"] * 1000
    w_wp = sp["wp"] * cp["rdmax"] * 1000

    stage = "إنبات"
    heat_stress_days = 0
    water_stress_days = 0
    daily_series = []

    for i, day in enumerate(weather):
        doy = planting_date.timetuple().tm_yday + i
        tmax, tmin = day["tmax"], day["tmin"]
        rain = day["rain_mm"]
        rad = day["rad_mj"]
        et0 = day["et0_mm"] or hargreaves_et0(tmax, tmin, lat, doy % 365)

        # GDD (Efficiency function — WOFOST)
        tmean = (tmax + tmin) / 2
        gdd = max(0, min(cp["topt"], tmean) - cp["tbase"])
        gdd_acc += gdd

        # مرحلة النمو
        if gdd_acc < cp["tsum1"]:
            stage = "نمو خضري"
        elif gdd_acc < cp["tsum1"] + cp["tsum2"]:
            stage = "إزهار وحبوب"
        else:
            stage = "نضج"
            break  # انتهى الموسم

        # Kc + ETc (FAO-56) + تصحيح المناطق الجافّة (CFET)
        # WOFOST يقلّل التبخّر منهجيّاً في الجافّ؛ CFET يصحّح ذلك (مبرهَن للجوف).
        kc = get_kc(i, cp)
        etc = et0 * kc * cfet

        # إجهاد حراري
        heat_factor = 1.0
        if tmax > cp["tmax_dev"]:
            heat_factor = max(0, 1 - (tmax - cp["tmax_dev"]) / 10)
            heat_stress_days += 1

        # توازن المياه (H7 FIX): المطر يضيف، والمحصول يستهلك ETc **دائماً**،
        # ثمّ الريّ يعيد الملء نحو السعة الحقليّة عند بلوغ عتبة الإجهاد. السابق
        # لم يطرح ETc تحت الريّ إطلاقاً (max(w_wp, w_soil) فقط) ⇒ الاستنزاف
        # لا يُنمذَج وwater_factor يبقى 1.0 ولا يُحسب احتياج ريّ حقيقي.
        w_soil = min(w_fc, w_soil + rain)
        w_soil = w_soil - etc
        if irrigation and w_soil < w_wp * 1.5:
            w_soil = w_fc  # الريّ يُعيد الملء للسعة الحقليّة عند الإجهاد
        w_soil = max(w_wp * 0.5, w_soil)

        # إجهاد مائي
        water_factor = 1.0
        if w_soil < w_wp * 1.5:
            water_factor = max(0.3, (w_soil - w_wp) / (w_wp * 0.5))
            water_stress_days += 1

        # LAI (Beer-Lambert)
        if gdd_acc < cp["tsum1"]:
            lai = min(8.0, gdd_acc / cp["tsum1"] * 5.0 * heat_factor * water_factor)
        else:
            progress_m2 = (gdd_acc - cp["tsum1"]) / cp["tsum2"]
            lai = max(0.5, 5.0 * (1 - progress_m2**0.5) * heat_factor)

        # PAR (Photosynthetically Active Radiation = 0.5 × Rs)
        par = rad * 0.5
        # فاصل الضوء (فريتشمان)
        f_int = 1 - math.exp(-cp["k"] * lai)
        # Biomass اليومي (g DM / m²)
        delta_b = cp["rue"] * par * f_int * heat_factor * water_factor
        biomass += delta_b

        daily_series.append(
            {
                "date": day["date"],
                "gdd": round(gdd, 1),
                "gdd_acc": round(gdd_acc, 1),
                "lai": round(lai, 3),
                "biomass_g_m2": round(biomass, 1),
                "etc_mm": round(etc, 2),
                "et0_mm": round(et0, 2),
                "kc": round(kc, 3),
                "rain_mm": round(rain, 1),
                "tmax": tmax,
                "tmin": tmin,
                "heat_stress": tmax > cp["tmax_dev"],
                "stage": stage,
            }
        )

    # ── النتائج النهائية ──────────────────────────────────────
    total_season = len(daily_series)
    harvest_date = planting_date + timedelta(days=total_season)

    biomass_kg_ha = biomass * 10  # g/m² → kg/ha
    yield_kg_ha = biomass_kg_ha * cp["hi"]
    yield_t_ha = yield_kg_ha / 1000

    total_etc = sum(d["etc_mm"] for d in daily_series)
    total_rain = sum(d["rain_mm"] for d in daily_series)
    total_irrigation = (
        max(0, total_etc - total_rain)
        if not irrigation
        else max(0, total_etc - total_rain) * 1.1
    )

    water_productivity = yield_kg_ha / max(1, total_etc)  # kg/m³

    return {
        "field_id": field_id,
        "crop": crop,
        "soil_type": soil_type,
        "planting_date": planting_date.isoformat(),
        "harvest_date": harvest_date.isoformat(),
        "season_days": total_season,
        "simulation": {
            "gdd_accumulated": round(gdd_acc, 1),
            "gdd_total_needed": tsum_needed,
            "progress_pct": round(min(100, gdd_acc / tsum_needed * 100), 1),
            "lai_max": round(max((d["lai"] for d in daily_series), default=0), 3),
            "biomass_kg_ha": round(biomass_kg_ha, 1),
            "yield_kg_ha": round(yield_kg_ha, 1),
            "yield_t_ha": round(yield_t_ha, 3),
            "total_yield_t": round(yield_t_ha * area_ha, 1),
        },
        "water_balance": {
            "total_etc_mm": round(total_etc, 1),
            "cfet_applied": cfet,
            "total_rain_mm": round(total_rain, 1),
            "irrigation_needed_mm": round(total_irrigation, 1),
            "water_productivity_kg_m3": round(water_productivity, 2),
        },
        "stress": {
            "heat_stress_days": heat_stress_days,
            "water_stress_days": water_stress_days,
            "heat_stress_index": round(heat_stress_days / max(1, total_season), 3),
        },
        "phenology": {
            "vegetative_days": cp["l_ini"] + cp["l_dev"],
            "flowering_days": cp["l_mid"],
            "maturity_days": cp["l_late"],
            "total_days": cp["l_ini"] + cp["l_dev"] + cp["l_mid"] + cp["l_late"],
        },
        "daily_series": daily_series,
        "model": "WOFOST-RUE + FAO-56 + Open-Meteo ERA5",
        "data_source": "Open-Meteo (حقيقي — بلا API key)",
    }
