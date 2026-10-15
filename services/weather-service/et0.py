"""et0.py — التبخّر-نتح المرجعيّ ET0 الموحَّد (FAO-56) + عقد جودة — WS-C.1b.

**كلّ ET0 من محرّك الطقس، من قلب الحساب لا من route.** يُبنى على بدائيّات الضغط
البخاري المشتركة (``vapor_pressure``) نفسها التي يستهلكها VPD (C.1a) — فصيغة e°/Δ
واحدة لا تتكرّر. الترتيب (قرار المستخدم): بدائيّات ضغط بخار → إشعاع → ثابت سيكرومتري
→ ميل SVP → FAO-56 Penman-Monteith → سياسة احتياط صريحة.

طريقتان، عقد جودة صريح لا يخلط بينهما:
  • ``fao56_penman_monteith`` (المرجع، ``validated``) — يتطلّب إشعاعاً + RH + رياحاً.
  • ``hargreaves_fallback`` (``degraded``) — عند نقص مدخلات PM؛ **لا يُقدَّم كـFAO-56**.
  • ``insufficient`` — لا حرارة/جغرافيا كافية (``et0_mm=None``، مفقود ≠ افتراض).

المخرَج: ``et0_mm`` · ``method`` · ``input_completeness`` · ``quality_status`` ·
``formula_version`` · ``missing_inputs`` · ``limitations``. نقيّ حتميّ، لا يرمي.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime

from vapor_pressure import (
    _RH_SENSOR_TOLERANCE_PCT,
    actual_vapor_pressure_from_rh_kpa,
    mean_saturation_vapor_pressure_kpa,
    svp_slope_kpa_per_c,
)

FORMULA_VERSION = "et0/fao56-pm/1.0.0"
PRODUCT_ID = "et0"
SNAPSHOT_SCHEME = "wsnap/sha1/1"

_MJ_TO_MM = 0.408  # تحويل الطاقة (MJ/m²/يوم) إلى مكافئ تبخّر (mm/يوم) — FAO-56.

# ── حدود المعقوليّة الفيزيائيّة للمُدخَلات (قرارات تُراجَع، مُسمّاة في موضع واحد) ──
# المُدخَل خارجها قراءةٌ مكسورة لا قياس: يُعلَن في ``invalid_inputs`` ولا يدخل الحساب.
# الحرارة: أدنى وأعلى ما سُجِّل على الأرض (−89.2°م، 56.7°م) بهامش.
_T_PLAUSIBLE_MIN_C = -90.0
_T_PLAUSIBLE_MAX_C = 60.0
# الارتفاع: ساحل البحر الميّت (≈−430 م) إلى قمّة إيفرست (≈8849 م) بهامش.
_ELEVATION_PLAUSIBLE_MIN_M = -450.0
_ELEVATION_PLAUSIBLE_MAX_M = 9000.0
# متوسّط الرياح اليوميّ على 2 م — ما فوقه خطأ وحدة/مستشعر لا طقس.
_WIND_2M_PLAUSIBLE_MAX_MS = 50.0
# الإشعاع الشمسيّ اليوميّ لا يتجاوز إشعاع السماء الصافية Rso (FAO-56 Eq. 37) إلّا
# بهامش قياس؛ ما فوقه خطأ وحدة (W/m² بدل MJ/m²/يوم مثلاً).
_SOLAR_OVER_RSO_TOLERANCE = 1.10


# ── بدائيّات الإشعاع ──
def extraterrestrial_radiation_mj(lat_deg: float, doy: int) -> float:
    """الإشعاع خارج الغلاف Ra (MJ/m²/يوم) — FAO-56 Eq. 21-25 (من خطّ العرض واليوم)."""
    lat = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi / 365 * doy)
    decl = 0.409 * math.sin(2 * math.pi / 365 * doy - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(lat) * math.tan(decl))))
    gsc = 0.0820
    return (
        (24 * 60 / math.pi)
        * gsc
        * dr
        * (ws * math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.sin(ws))
    )


# ── ثابت سيكرومتري ──
def psychrometric_constant_kpa_per_c(elevation_m: float) -> float:
    """γ (kPa/°C) — FAO-56 Eq. 7-8: من الضغط الجوّي المشتقّ من الارتفاع."""
    p = 101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26
    return 0.000665 * p


def penman_monteith_et0_mm(
    *,
    t_max_c: float,
    t_min_c: float,
    t_mean_c: float,
    solar_rad_mj_m2: float,
    rh_mean_pct: float,
    wind_2m_ms: float,
    lat_deg: float,
    elevation_m: float,
    doy: int,
) -> float:
    """FAO-56 Penman-Monteith (Eq. 6) — يستهلك بدائيّات الضغط البخاري المشتركة."""
    es = mean_saturation_vapor_pressure_kpa(t_max_c, t_min_c)
    ea = actual_vapor_pressure_from_rh_kpa(es, rh_mean_pct)
    delta = svp_slope_kpa_per_c(t_mean_c)
    gamma = psychrometric_constant_kpa_per_c(elevation_m)
    rns = (1.0 - 0.23) * solar_rad_mj_m2
    ra = extraterrestrial_radiation_mj(lat_deg, doy)
    rso = (0.75 + 2e-5 * elevation_m) * ra
    rs_rso = min(1.0, solar_rad_mj_m2 / rso) if rso > 0 else 1.0
    tmaxk = t_max_c + 273.16
    tmink = t_min_c + 273.16
    rnl = (
        4.903e-9
        * (tmaxk**4 + tmink**4)
        / 2.0
        * (0.34 - 0.14 * math.sqrt(max(0.0, ea)))
        * (1.35 * rs_rso - 0.35)
    )
    rn = rns - rnl
    num = 0.408 * delta * rn + gamma * 900.0 / (t_mean_c + 273.0) * wind_2m_ms * (es - ea)
    den = delta + gamma * (1.0 + 0.34 * wind_2m_ms)
    return max(0.0, num / den)


def hargreaves_et0_mm(*, t_max_c: float, t_min_c: float, lat_deg: float, doy: int) -> float:
    """Hargreaves-Samani (FAO-56 Eq. 52) — احتياط عند نقص مدخلات PM.

    ET0 = 0.0023 · (Tmean+17.8) · √(Tmax−Tmin) · Ra_mm — أقلّ دقّة من PM (degraded).
    """
    tmean = (t_max_c + t_min_c) / 2.0
    td = max(0.0, t_max_c - t_min_c)
    ra_mm = extraterrestrial_radiation_mj(lat_deg, doy) * _MJ_TO_MM
    return max(0.0, 0.0023 * (tmean + 17.8) * math.sqrt(td) * ra_mm)


def _finite(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _valid_doy(v) -> int | None:
    """يوم السنة الصالح: عدد صحيح (لا bool) في [1, 366]، وإلّا ``None``."""
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    return v if 1 <= v <= 366 else None


def compute_et0(
    *,
    t_max_c: float | None,
    t_min_c: float | None,
    solar_rad_mj_m2: float | None = None,
    rh_mean_pct: float | None = None,
    wind_2m_ms: float | None = None,
    t_mean_c: float | None = None,
    lat_deg: float | None = None,
    elevation_m: float | None = None,
    day_of_year: int | None = None,
) -> dict:
    """يحسب ET0 بعقد جودة صريح: PM عند اكتمال المدخلات، وإلّا Hargreaves (degraded).

    صدق: لا يُقدَّم Hargreaves كـFAO-56 · مفقود ≠ افتراض · غير-محدود ⇒ يُهمَل المدخل.
    """
    tmax, tmin = _finite(t_max_c), _finite(t_min_c)
    solar, rh, wind = _finite(solar_rad_mj_m2), _finite(rh_mean_pct), _finite(wind_2m_ms)
    lat, elev = _finite(lat_deg), _finite(elevation_m)
    tmean = _finite(t_mean_c)

    base = {
        "product": PRODUCT_ID,
        "formula_version": FORMULA_VERSION,
        "unit": "mm/day",
        "et0_mm": None,
    }

    # ── المعقوليّة الفيزيائيّة: قراءةٌ مكسورة تُعلَن ولا تدخل الحساب ──
    # (مفقود ≠ مكسور: المفقود في ``missing_inputs``، والمكسور في ``invalid_inputs``
    # بسببه — فلا يُحسب ET0 «validated» من مُدخَل مستحيل، ولا ترمي الدالّة.)
    invalid: list[str] = []
    reasons: list[str] = []

    def _reject(name: str, why: str) -> None:
        invalid.append(name)
        reasons.append(f"{name} rejected: {why}")

    doy = None
    if day_of_year is not None:
        doy = _valid_doy(day_of_year)
        if doy is None:
            _reject("day_of_year", "must be an integer in [1, 366]")
    if lat is not None and not -90.0 <= lat <= 90.0:
        _reject("lat_deg", "outside [-90, 90]")
        lat = None
    for name, val in (("t_max_c", tmax), ("t_min_c", tmin)):
        if val is not None and not _T_PLAUSIBLE_MIN_C <= val <= _T_PLAUSIBLE_MAX_C:
            _reject(name, f"outside plausible [{_T_PLAUSIBLE_MIN_C}, {_T_PLAUSIBLE_MAX_C}] °C")
    if "t_max_c" in invalid:
        tmax = None
    if "t_min_c" in invalid:
        tmin = None
    if tmax is not None and tmin is not None and tmax < tmin:
        _reject("t_max_c", "t_max_c < t_min_c")
        _reject("t_min_c", "t_max_c < t_min_c")
        tmax = tmin = None

    # الحدّ الأدنى المطلق: حرارتان + جغرافيا (خطّ عرض + يوم) لحساب Ra.
    missing_core = [
        n
        for n, v in (("t_max_c", tmax), ("t_min_c", tmin), ("lat_deg", lat), ("day_of_year", doy))
        if v is None and n not in invalid
    ]
    if missing_core or invalid:
        return {
            **base,
            "method": "insufficient",
            "input_completeness": 0.0,
            "quality_status": "insufficient",
            "missing_inputs": missing_core,
            "invalid_inputs": invalid,
            "limitations": ["cannot compute ET0 without temperature + geography", *reasons],
        }

    if tmean is not None and not tmin <= tmean <= tmax:
        _reject("t_mean_c", "outside [t_min_c, t_max_c]; derived from t_max_c/t_min_c instead")
        tmean = None
    if tmean is None:
        tmean = (tmax + tmin) / 2.0
    if elev is not None and not _ELEVATION_PLAUSIBLE_MIN_M <= elev <= _ELEVATION_PLAUSIBLE_MAX_M:
        _reject(
            "elevation_m",
            f"outside plausible [{_ELEVATION_PLAUSIBLE_MIN_M}, {_ELEVATION_PLAUSIBLE_MAX_M}] m",
        )
        elev = None
    elev_v = elev if elev is not None else 0.0

    # مُدخَلات PM: المكسور منها يُعامَل كغائب عن المسار المرجعيّ (لا يُقصّ إلى قيمة).
    if rh is not None and not (-_RH_SENSOR_TOLERANCE_PCT <= rh <= 100.0 + _RH_SENSOR_TOLERANCE_PCT):
        _reject("rh_mean_pct", "outside sensor-noise range; a broken reading is not clamped")
        rh = None
    if wind is not None and not 0.0 <= wind <= _WIND_2M_PLAUSIBLE_MAX_MS:
        _reject("wind_2m_ms", f"outside plausible [0, {_WIND_2M_PLAUSIBLE_MAX_MS}] m/s")
        wind = None
    if solar is not None:
        ra_mj = extraterrestrial_radiation_mj(lat, doy)
        rso_mj = (0.75 + 2e-5 * elev_v) * ra_mj
        if solar < 0.0:
            _reject("solar_rad_mj_m2", "negative")
            solar = None
        elif solar == 0.0 and ra_mj > 0.0:
            _reject(
                "solar_rad_mj_m2", "zero daily radiation while Ra > 0 (absence, not a measurement)"
            )
            solar = None
        elif solar > _SOLAR_OVER_RSO_TOLERANCE * rso_mj:
            _reject(
                "solar_rad_mj_m2", "exceeds clear-sky Rso (FAO-56 Eq. 37); unit or sensor error"
            )
            solar = None

    # مدخلات PM الإضافيّة (إشعاع + RH + رياح). اكتمالها ⇒ المسار المرجعيّ.
    pm_missing = [
        n
        for n, v in (("solar_rad_mj_m2", solar), ("rh_mean_pct", rh), ("wind_2m_ms", wind))
        if v is None
    ]

    if not pm_missing:
        et0 = penman_monteith_et0_mm(
            t_max_c=tmax,
            t_min_c=tmin,
            t_mean_c=tmean,
            solar_rad_mj_m2=solar,
            rh_mean_pct=rh,
            wind_2m_ms=wind,
            lat_deg=lat,
            elevation_m=elev_v,
            doy=doy,
        )
        limitations = [] if elev is not None else ["elevation defaulted to 0 m (sea level)"]
        return {
            **base,
            "et0_mm": round(et0, 3),
            "method": "fao56_penman_monteith",
            "input_completeness": 1.0,
            "quality_status": "validated",
            "missing_inputs": [],
            "invalid_inputs": invalid,
            "limitations": [*limitations, *reasons],
        }

    # احتياط Hargreaves — صريح، degraded، لا يُقدَّم كـFAO-56.
    # المرفوض ليس «مفقوداً»: يبقى في ``invalid_inputs`` وحده، ويُحسب غيابه في الاكتمال.
    et0 = hargreaves_et0_mm(t_max_c=tmax, t_min_c=tmin, lat_deg=lat, doy=doy)
    label = "missing or rejected" if any(n in invalid for n in pm_missing) else "missing"
    return {
        **base,
        "et0_mm": round(et0, 3),
        "method": "hargreaves_fallback",
        "input_completeness": round((3 - len(pm_missing)) / 3.0, 2),
        "quality_status": "degraded",
        "missing_inputs": [n for n in pm_missing if n not in invalid],
        "invalid_inputs": invalid,
        "limitations": [
            f"Penman-Monteith inputs {label} ("
            + ", ".join(pm_missing)
            + ") — Hargreaves fallback used; NOT full FAO-56.",
            *reasons,
        ],
    }


def _doy_from_iso_date(value) -> int | None:
    """day-of-year من تاريخ ISO (YYYY-MM-DD) — المحرّك يملك التقويم/الفلك.

    التاريخ هو الحقيقة وDOY مشتقّ؛ فحين يمرّر المُستهلِك تواريخ فعليّة (سجلّ متفرّق/
    متعدّد السنوات) يحسب المحرّك DOY لكلّ يوم بلا انجراف. تاريخ تالف ⇒ ``None``.
    """
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").timetuple().tm_yday
    except (ValueError, TypeError):
        return None


def et0_series_product(
    *,
    daily_t_min: list,
    daily_t_max: list,
    lat_deg: float | None,
    elevation_m: float | None = None,
    daily_solar_rad_mj_m2: list | None = None,
    daily_rh_mean_pct: list | None = None,
    daily_wind_2m_ms: list | None = None,
    day_of_year_start: int | None = None,
    daily_dates: list | None = None,
    valid_period: dict | None = None,
) -> dict:
    """سلسلة ET0 يوميّة مرجعيّة (FAO-56) — نواة المحرّك لسلاسل الموسم/المحاكاة.

    يجنّب N نداءات مفردة: يحسب ET0 لكلّ يوم بنفس ``compute_et0`` (fao56-pm عند اكتمال
    المدخلات وإلّا Hargreaves degraded). **مصدر day-of-year (بالأولويّة):** ``daily_dates``
    (تاريخ ISO لكلّ يوم ⇒ المحرّك يحسب DOY الحقيقيّ — يمنع الانجراف الفلكيّ في السجلّات
    المتفرّقة/متعدّدة السنوات) وإلّا ``day_of_year_start`` متزايداً تسلسليّاً. نقيّ حتميّ.
    يعيد ``daily_et0_mm`` (قد يحوي None ليوم ناقص) + ``methods`` + ``accumulated_et0_mm`` +
    عقد الخدمة (formula_version/valid_period).
    """
    n = min(len(daily_t_min), len(daily_t_max))
    solar = daily_solar_rad_mj_m2 or []
    rh = daily_rh_mean_pct or []
    wind = daily_wind_2m_ms or []
    dates = daily_dates or []
    daily_et0: list[float | None] = []
    methods: list[str] = []
    total = 0.0
    counted = 0
    for i in range(n):
        # التاريخ الفعليّ (إن مُرِّر) هو الحقيقة؛ وإلّا DOY تسلسليّ (سلسلة متّصلة).
        doy = _doy_from_iso_date(dates[i]) if i < len(dates) else None
        if doy is None:
            doy = (day_of_year_start + i) if day_of_year_start is not None else None
        res = compute_et0(
            t_max_c=daily_t_max[i],
            t_min_c=daily_t_min[i],
            solar_rad_mj_m2=solar[i] if i < len(solar) else None,
            rh_mean_pct=rh[i] if i < len(rh) else None,
            wind_2m_ms=wind[i] if i < len(wind) else None,
            lat_deg=lat_deg,
            elevation_m=elevation_m,
            day_of_year=doy,
        )
        val = res.get("et0_mm")
        daily_et0.append(val)
        methods.append(res.get("method"))
        if val is not None:
            total += val
            counted += 1
    return {
        "product": "et0_series",
        "formula_version": FORMULA_VERSION,
        "unit": "mm/day",
        "daily_et0_mm": daily_et0,
        "methods": methods,
        "accumulated_et0_mm": round(total, 3),
        "days": n,
        "days_computed": counted,
        "valid_period": valid_period,
    }


def weather_snapshot_id(inputs: dict) -> str:
    """بصمة حتميّة لمتّجه الطقس المُستخدَم — هويّة اللقطة (لا زمن/عشوائيّة).

    نفس الطقس ⇒ نفس المُعرِّف (يفيد shadow-compare والـdedup). في هذه المرحلة
    اللقطة يُوفّرها المُستهلِك؛ حين يملك المحرّك جلب اللقطة (WS-D.2c) يأتي المُعرِّف
    من نَسَب اللقطة المجلوبة. الصيغة: sha1 لـJSON مقنَّن للمدخلات المُقرَّبة.
    """
    canonical = {
        k: (round(v, 4) if isinstance(v, float) else v)
        for k, v in sorted(inputs.items())
        if v is not None
    }
    # بصمة/هويّة لا أمان تعميّة — usedforsecurity=False يُرضي bandit B324 وruff S324.
    digest = hashlib.sha1(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:16]
    return f"{SNAPSHOT_SCHEME}:{digest}"


def et0_agro_product(
    *,
    t_max_c: float | None,
    t_min_c: float | None,
    solar_rad_mj_m2: float | None = None,
    rh_mean_pct: float | None = None,
    wind_2m_ms: float | None = None,
    t_mean_c: float | None = None,
    lat_deg: float | None = None,
    elevation_m: float | None = None,
    day_of_year: int | None = None,
    valid_time: str | None = None,
    weather_snapshot_id_override: str | None = None,
) -> dict:
    """منتج ET0 الزراعيّ لعقد محرّك الطقس — ``compute_et0`` + نَسَب الخدمة.

    يضيف على عقد الجودة الحسابيّ حقلَي نَسَب لا يختلقهما: ``valid_time`` (وقت صلاحيّة
    اللقطة كما يُصرّح به المُستهلِك؛ مفقود ⇒ None + قيد) و``weather_snapshot_id``
    (بصمة متّجه الطقس). **صدق:** المحرّك يملك تنفيذ الصيغة؛ اللقطة يُوفّرها المُستهلِك
    في هذه المرحلة (يُصرَّح صراحةً كقيد حتّى WS-D.2c جلب اللقطة داخل المحرّك).
    """
    result = compute_et0(
        t_max_c=t_max_c,
        t_min_c=t_min_c,
        solar_rad_mj_m2=solar_rad_mj_m2,
        rh_mean_pct=rh_mean_pct,
        wind_2m_ms=wind_2m_ms,
        t_mean_c=t_mean_c,
        lat_deg=lat_deg,
        elevation_m=elevation_m,
        day_of_year=day_of_year,
    )
    snapshot_inputs = {
        "t_max_c": t_max_c,
        "t_min_c": t_min_c,
        "solar_rad_mj_m2": solar_rad_mj_m2,
        "rh_mean_pct": rh_mean_pct,
        "wind_2m_ms": wind_2m_ms,
        "t_mean_c": t_mean_c,
        "lat_deg": lat_deg,
        "elevation_m": elevation_m,
        "day_of_year": day_of_year,
    }
    snap_id = weather_snapshot_id_override or weather_snapshot_id(snapshot_inputs)
    limitations = list(result.get("limitations", []))
    if valid_time is None:
        limitations = [*limitations, "valid_time not supplied by consumer"]
    return {
        **result,
        "limitations": limitations,
        "valid_time": valid_time,
        "weather_snapshot_id": snap_id,
        "snapshot_source": "consumer_supplied_inputs",
    }
