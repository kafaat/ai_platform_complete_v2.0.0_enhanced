"""canonical_weather_state.py — WX-10.1: CanonicalWeatherState كـ**State Product** موحَّد.

الحقيقة الوحيدة للطقس: منتَج حالة (State Product) لا مجرَّد DTO. يحمل غلافاً صريحاً
(`state_id · state_version · schema_version · owner · source_snapshot_id · generated_at ·
quality · availability · confidence · provenance · evidence · limitations`) ثمّ **يجمع**
منتجات المحرّك القائمة (ET0 · VPD · GDD · astronomy · DTR) **دون إعادة حسابها** — يستدعي
دوالّها المُتعاقَد عليها (`et0_agro_product`/`compute_vpd`/`gdd_agro_product`/
`extraterrestrial_radiation_mj`) ويلفّ نتائجها.

**الانعكاس المعماريّ (WX-10):** الهدف أن تصير ET0/VPD/GDD/… *مشتقّات (Views)* من هذه الحالة
لا العكس — كلّ مستهلك يقرأ CanonicalWeatherState لا المحرّك مباشرةً. هذا الإنكرمنت (WX-10.1)
يبني **العقد + المُجمِّع** فقط (إضافيّ، بلا إعادة توصيل مستهلكين)؛ تحويل كلّ مشتقّ إلى View
مستقلّ إنكرمنت تالٍ.

**نقيّ حتميّ fail-closed:** لا I/O، لا numpy، لا اختلاق. غياب المدخلات لمنتَج ⇒ `availability`
لذلك المنتَج = false + قيد صريح، **لا قيمة مُختلقة**. `generated_at` = `valid_time` الذي يُصرّح
به المُستهلِك (لا ساعة حائط مُختلقة). المُجمِّع لا يرمي أبداً — يعكس عقود الجودة للمنتجات.
"""

from __future__ import annotations

import hashlib
import json
import math

from et0 import et0_agro_product, extraterrestrial_radiation_mj, weather_snapshot_id
from gdd import gdd_agro_product
from vpd import compute_vpd

PRODUCT_ID = "canonical_weather_state"
OWNER = "weather-service"
# مُعرِّف العقد (الشكل) — يفحصه الحارس. تغيير شكل الغلاف = إصدار جديد.
SCHEMA_VERSION = "wx10/canonical-weather-state/1.0.0"
# إصدار عقد الحالة (semver) — يُثبِّته المستهلك للنَّسَب. يتزامن مع SCHEMA_VERSION.
STATE_VERSION = "1.0.0"

# كلّ خانات الحالة وفق مواصفة WX-10 — تُصرَّح كلّها في availability (لا استنتاج null).
# WX-10.1 يجمع الخانات النقيّة القابلة للاشتقاق من المدخلات؛ الباقي (I/O أو سلاسل) يُصرَّح
# غيرَ متوفّر صراحةً بقيد — يُوصَّل في إنكرمنتات تالية (لا ادّعاء تغطية زائف).
_COMPOSED_SLOTS = ("et0", "vpd", "gdd", "astronomy", "dtr")
_DEFERRED_SLOTS = (
    "current",
    "forecast",
    "historical",
    "heat_load",
    "chill_hours",
    "frost_risk",
    "operation_windows",
)
STATE_SLOTS = (*_COMPOSED_SLOTS, *_DEFERRED_SLOTS)

# ترتيب شدّة الجودة لأخذ الأسوأ بين المنتجات المتوفّرة (يوحّد مفردات et0/vpd/gdd).
_SEVERITY = {
    "validated": 0,
    "ok": 0,
    "degraded": 1,
    "hargreaves_fallback": 1,
    "inconsistent_inputs": 2,
    "insufficient": 3,
    "invalid": 4,
    None: 3,
}
# حالات تعني «المنتَج غير متوفّر» (availability=false) — لا قيمة صالحة للاستهلاك.
_UNAVAILABLE_STATUSES = {"insufficient", "invalid", None}


def _finite(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _worse(a: str | None, b: str | None) -> str | None:
    """يُرجِع الأسوأ (الأعلى شدّةً) بين حالتَي جودة وفق `_SEVERITY`."""
    sa = _SEVERITY.get(a, 3)
    sb = _SEVERITY.get(b, 3)
    return a if sa >= sb else b


def _is_available(status: str | None) -> bool:
    return status not in _UNAVAILABLE_STATUSES


def _confidence_from_quality(status: str | None) -> str:
    """مستوى ثقة مُشتقّ من جودة الحالة الكلّيّة — صريح لا مُختلق."""
    if status in ("validated", "ok"):
        return "high"
    if status in ("degraded", "hargreaves_fallback"):
        return "medium"
    return "low"


def _canonical_inputs(inputs: dict) -> str:
    """تمثيل حتميّ مُرتَّب للمدخلات غير-None (لبصمة الحالة)."""
    clean = {k: v for k, v in sorted(inputs.items()) if v is not None}
    return json.dumps(clean, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _astronomy_product(*, lat_deg: float | None, day_of_year: int | None) -> dict:
    """منتَج فلكيّ نقيّ: Ra خارج الغلاف + طول النهار — من (خطّ العرض + يوم السنة).

    يفوّض حساب Ra للنواة الكنسيّة `et0.extraterrestrial_radiation_mj` (لا إعادة تنفيذ).
    غياب lat/doy ⇒ insufficient (لا افتراض). طول النهار FAO-56 eq. 34.
    """
    lat = _finite(lat_deg)
    doy = (
        day_of_year if isinstance(day_of_year, int) and not isinstance(day_of_year, bool) else None
    )
    if lat is None or doy is None or not (1 <= doy <= 366):
        return {
            "product": "astronomy",
            "ra_mj_m2_day": None,
            "daylight_hours": None,
            "day_of_year": doy,
            "quality_status": "insufficient",
            "limitations": ["astronomy requires latitude + day_of_year (1..366)"],
        }
    ra = extraterrestrial_radiation_mj(lat, doy)
    decl = 0.409 * math.sin(2 * math.pi / 365 * doy - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(math.radians(lat)) * math.tan(decl))))
    daylight = 24.0 / math.pi * ws
    return {
        "product": "astronomy",
        "ra_mj_m2_day": round(ra, 4),
        "daylight_hours": round(daylight, 3),
        "day_of_year": doy,
        "quality_status": "validated",
        "limitations": [],
    }


def _dtr_product(*, t_max_c: float | None, t_min_c: float | None) -> dict:
    """المدى الحراريّ اليوميّ DTR = Tmax − Tmin — نقيّ. مفقود/غير محدود ⇒ insufficient."""
    tmax, tmin = _finite(t_max_c), _finite(t_min_c)
    if tmax is None or tmin is None:
        return {
            "product": "dtr",
            "dtr_c": None,
            "quality_status": "insufficient",
            "limitations": ["DTR requires finite t_max_c and t_min_c"],
        }
    if tmax < tmin:
        return {
            "product": "dtr",
            "dtr_c": None,
            "quality_status": "invalid",
            "limitations": [f"t_max_c ({tmax}) < t_min_c ({tmin}) — inconsistent inputs"],
        }
    return {
        "product": "dtr",
        "dtr_c": round(tmax - tmin, 3),
        "quality_status": "validated",
        "limitations": [],
    }


def build_canonical_weather_state(
    *,
    t_max_c: float | None = None,
    t_min_c: float | None = None,
    t_mean_c: float | None = None,
    rh_mean_pct: float | None = None,
    dew_point_c: float | None = None,
    wind_2m_ms: float | None = None,
    solar_rad_mj_m2: float | None = None,
    lat_deg: float | None = None,
    elevation_m: float | None = None,
    day_of_year: int | None = None,
    gdd_daily_t_min: list | None = None,
    gdd_daily_t_max: list | None = None,
    gdd_base_c: float | None = None,
    gdd_upper_cutoff_c: float | None = None,
    gdd_method: str = "modified",
    gdd_start_date: str | None = None,
    gdd_end_date: str | None = None,
    valid_time: str | None = None,
    weather_snapshot_id_override: str | None = None,
) -> dict:
    """يبني CanonicalWeatherState بجمع منتجات المحرّك القائمة (بلا إعادة حساب).

    كلّ منتَج فرعيّ يُستدعى عبر دالّته المُتعاقَد عليها (لا يرمي)؛ الغلاف يجمع الجودة الأسوأ،
    خريطة `availability` كاملة على كلّ الخانات، `provenance` لكلّ منتَج متوفّر، `evidence`
    = المدخلات المُستخدَمة فعلاً، و`limitations` مُوحَّدة. لا اختلاق: خانة بلا مدخلات ⇒
    غير متوفّرة + قيد.
    """
    et0 = et0_agro_product(
        t_max_c=t_max_c,
        t_min_c=t_min_c,
        solar_rad_mj_m2=solar_rad_mj_m2,
        rh_mean_pct=rh_mean_pct,
        wind_2m_ms=wind_2m_ms,
        t_mean_c=t_mean_c,
        lat_deg=lat_deg,
        elevation_m=elevation_m,
        day_of_year=day_of_year,
        valid_time=valid_time,
        weather_snapshot_id_override=weather_snapshot_id_override,
    )
    vpd = compute_vpd(
        t_max_c=t_max_c,
        t_min_c=t_min_c,
        rh_mean_pct=rh_mean_pct,
        dew_point_c=dew_point_c,
    )
    gdd = gdd_agro_product(
        daily_t_min=gdd_daily_t_min or [],
        daily_t_max=gdd_daily_t_max or [],
        base_c=gdd_base_c,
        upper_cutoff_c=gdd_upper_cutoff_c,
        method=gdd_method,
        start_date=gdd_start_date,
        end_date=gdd_end_date,
    )
    astronomy = _astronomy_product(lat_deg=lat_deg, day_of_year=day_of_year)
    dtr = _dtr_product(t_max_c=t_max_c, t_min_c=t_min_c)

    composed = {"et0": et0, "vpd": vpd, "gdd": gdd, "astronomy": astronomy, "dtr": dtr}

    # بصمة النَّسَب: مصدرها متّجه الطقس (نفس دالّة et0 لتوحيد هويّة اللقطة).
    snapshot_inputs = {
        "t_max_c": t_max_c,
        "t_min_c": t_min_c,
        "solar_rad_mj_m2": solar_rad_mj_m2,
        "rh_mean_pct": rh_mean_pct,
        "wind_2m_ms": wind_2m_ms,
        "t_mean_c": t_mean_c,
        "dew_point_c": dew_point_c,
        "lat_deg": lat_deg,
        "elevation_m": elevation_m,
        "day_of_year": day_of_year,
    }
    # لقطة المصدر للحالة: إن صرّح المُستهلِك بمعرِّف لقطة (override) فهو الحقيقة —
    # يدخل source_snapshot_id (فيتماسك مع products.et0.weather_snapshot_id) **و**state_id
    # (فيتمايز طلبان بنفس القيم لكن بلقطتين مختلفتين — traceability/replay/dedup سليمة).
    source_snapshot_id = weather_snapshot_id_override or weather_snapshot_id(snapshot_inputs)

    availability: dict[str, bool] = {}
    provenance: dict[str, dict] = {}
    limitations: list[str] = []
    overall_quality: str | None = None

    for slot in _COMPOSED_SLOTS:
        prod = composed[slot]
        status = prod.get("quality_status")
        avail = _is_available(status)
        availability[slot] = avail
        for lim in prod.get("limitations", []) or []:
            tagged = f"{slot}: {lim}"
            if tagged not in limitations:
                limitations.append(tagged)
        if avail:
            overall_quality = status if overall_quality is None else _worse(overall_quality, status)
            provenance[slot] = {
                "quality_status": status,
                "method": prod.get("method") or prod.get("thresholds_used", {}).get("method"),
                "formula_version": (
                    prod.get("formula_version")
                    or prod.get("calculation_version")
                    or prod.get("version")
                ),
                "weather_snapshot_id": prod.get("weather_snapshot_id"),
            }

    for slot in _DEFERRED_SLOTS:
        availability[slot] = False
        limitations.append(
            f"{slot}: not composed by the pure WX-10.1 assembler "
            "(requires I/O or series) — scheduled for a later increment"
        )

    # لا منتَج متوفّر ⇒ الحالة نفسها insufficient (fail-closed، لا اختلاق قيمة كلّيّة).
    if overall_quality is None:
        overall_quality = "insufficient"

    evidence = {k: v for k, v in snapshot_inputs.items() if v is not None}
    if gdd_base_c is not None:
        evidence["gdd_base_c"] = gdd_base_c

    # بصمة هويّة/نَسَب حتميّة — ليست هاشاً أمنيّاً (لا سلامة/توثيق) ⇒ usedforsecurity=False.
    state_id = hashlib.sha1(
        f"{source_snapshot_id}:{SCHEMA_VERSION}:{_canonical_inputs(snapshot_inputs)}".encode(),
        usedforsecurity=False,
    ).hexdigest()[:16]

    return {
        "product_id": PRODUCT_ID,
        "state_id": state_id,
        "state_version": STATE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "owner": OWNER,
        "source_snapshot_id": source_snapshot_id,
        "generated_at": valid_time,  # وقت الصلاحيّة كما صرّح به المُستهلِك (لا ساعة مُختلقة)
        "quality": overall_quality,
        "confidence": _confidence_from_quality(overall_quality),
        "availability": availability,
        "provenance": provenance,
        "evidence": evidence,
        "limitations": limitations,
        "products": composed,
    }


def weather_state_report(state: dict) -> dict:
    """مستهلك WX-10.1 (إثبات التصميم): تقرير مُشتقّ **يقرأ الحالة فقط** — لا يستدعي المحرّك.

    يثبت الانعكاس المعماريّ على View واحد: التقرير لا يعرف ET0/VPD/GDD كنوى، بل يقرأ
    CanonicalWeatherState (`availability`/`quality`/`products`/النَّسَب) ويُلخّصها. أيّ قرار/
    تقرير لاحق يستطيع الإشارة إلى `state_id`/`source_snapshot_id` التي بُني عليها (lineage).
    """
    availability = state.get("availability", {})
    products = state.get("products", {})
    available = sorted(k for k, v in availability.items() if v)
    unavailable = sorted(k for k, v in availability.items() if not v)

    headline: dict[str, float | None] = {}
    if availability.get("et0"):
        headline["et0_mm"] = products.get("et0", {}).get("et0_mm")
    if availability.get("vpd"):
        headline["vpd_kpa"] = products.get("vpd", {}).get("vpd_kpa")
    if availability.get("gdd"):
        headline["accumulated_gdd"] = products.get("gdd", {}).get("accumulated_gdd")
    if availability.get("dtr"):
        headline["dtr_c"] = products.get("dtr", {}).get("dtr_c")
    if availability.get("astronomy"):
        headline["daylight_hours"] = products.get("astronomy", {}).get("daylight_hours")

    return {
        "report_id": "weather_state_report",
        "reads_from": "canonical_weather_state",  # لا يقرأ المحرّك مباشرةً — العقد يُثبت ذلك
        "state_id": state.get("state_id"),
        "state_version": state.get("state_version"),
        "source_snapshot_id": state.get("source_snapshot_id"),
        "generated_at": state.get("generated_at"),
        "overall_quality": state.get("quality"),
        "confidence": state.get("confidence"),
        "available_products": available,
        "unavailable_products": unavailable,
        "headline": headline,
        "limitations": list(state.get("limitations", [])),
    }


def et0_view(state: dict) -> dict:
    """WX-10.2 — منتَج ET0 كـ**View مُشتقّ من CanonicalWeatherState** (لا نواة مباشرة).

    الانعكاس المعماريّ مُطبَّقاً على ET0: بدل حساب ET0 من المحرّك مباشرةً، يُشتقّ من خانة
    `et0` في الحالة الكنسيّة (نفس حقول العقد بدقّة — حفظ سلوك) **مضافاً إليها نَسَب الحالة**
    (`canonical_state_id`/`source_snapshot_id`/`canonical_state_version`) فيربط أيّ مستهلك
    ET0 بنسخة حالة الطقس التي اشتُقّ منها. توافقيّ للخلف: مجموعة فائقة (يُضيف لا يحذف).
    """
    et0 = dict(state.get("products", {}).get("et0", {}))
    et0["derived_from"] = "canonical_weather_state"
    et0["canonical_state_id"] = state.get("state_id")
    et0["canonical_state_version"] = state.get("state_version")
    # بصمة اللقطة المصدر للحالة (نَسَب) — قد تساوي weather_snapshot_id للمنتَج أو تتمايز
    # حين يُمرّر المُستهلِك override؛ كلاهما صريح.
    et0["source_snapshot_id"] = state.get("source_snapshot_id")
    return et0
