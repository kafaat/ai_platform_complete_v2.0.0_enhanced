"""SAHOOL agriai-engine — pcse_inputs.py (وحدة صرفة: لا pcse ولا FastAPI ولا شبكة).

بُناة مدخلات PCSE/WOFOST 7.2 من عقد طلب ``/v1/simulate``. كانت البُناة في ``wofost_adapter``
أقلاباً — مقيس 2026-09-29 على pcse 6.0.13: dict الإدارة يُمرَّر خامّاً فيسقط
``AgroManager.initialize`` بـ``'str' object has no attribute 'keys'``، وموفِّر الطقس يُعاد
**صنفاً** لا نسخةً مملوءة، و``sitedata={}``، والتربة dict خامّ بلا معاملات ``WaterbalanceFD``.
هنا تُبنى البنى بالشكل الذي تقرؤه PCSE وبوحداتها، ويُرفَض النقص **باسمه**
(``SimulationInputError`` ⇒ 422) بدل اختلاقه.

**عقد اليوم الواحد في ``weather.daily``** (مفتاح واحد لكلّ متغيّر ووحدة معلنة):

    date                   ISO YYYY-MM-DD            ⇒ DAY
    tmin / tmax            °C                        ⇒ TMIN / TMAX
    rain_mm                mm/يوم                    ⇒ RAIN  (cm/يوم = mm / 10)
    solar_radiation_mj_m2  MJ/m²/يوم                 ⇒ IRRAD (J/m²/يوم = MJ × 10⁶)
    vapour_pressure_hpa    hPa   | أحدهما فقط        ⇒ VAP   (hPa)
    vapour_pressure_kpa    kPa   |                   ⇒ VAP   (hPa = kPa × 10)
    wind_2m_m_s            m/s على 2 م | أحدهما فقط  ⇒ WIND  (m/s على 2 م، كما هو)
    wind_10m_m_s           m/s على 10 م |            ⇒ WIND  (يُحوَّل في طبقة pcse بـ``wind10to2``)

وعلى مستوى ``weather``: ``latitude`` · ``longitude`` · ``elevation_m`` (إلزاميّة: حقول
``WeatherDataContainer``)، و``angstrom_a``/``angstrom_b`` اختياريّان معاً.

**ما لا يُحسب هنا عمداً** — لا صيغة طقس في SAHOOL خارج محرّك الطقس
(``scripts/ci/weather_engine_formula_guard.py``)، فكلّ اشتقاقٍ يُترك لمالكه:
  • E0/ES0/ET0 ⇐ ``pcse.util.reference_ET`` في طبقة pcse (كما يفعل موفِّرا CSV/Excel في PCSE).
  • رياح 10 م ⇒ 2 م ⇐ ``pcse.util.wind10to2`` (اصطلاح موفِّر Open-Meteo في PCSE نفسه).
  • ضغط البخار من الرطوبة أو نقطة الندى **لا يُشتقّ هنا أصلاً**: يُطلب ضغطُ البخار نفسه
    (منتَج محرّك الطقس ``ea_kpa`` ⇒ ``vapour_pressure_kpa``). و``wind_m_s`` بلا ارتفاعٍ مُعلَن
    لا يُفترَض 2 م — يومٌ بلا أحدهما ⇒ ``weather_day_missing`` لا تقدير.

حدود المدى المنسوخة هنا (مدى الطقس، أنغستروم، ``WAV``) هي حدود PCSE 6.0.13 نفسها بمراجعها،
ويقارنها اختبار التكامل بمصدرها حين تتوفّر pcse — كي يُرفَض المدخل هنا باسمه (422) لا داخل
PCSE حيث يصير ``PCSEError`` عامّاً (503).
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from itertools import pairwise
from typing import Any, NoReturn

import sim_crop_registry

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_HERE, "pcse_data")
CROP_DIR = os.path.join(DATA_DIR, "wofost72_crop")
DEFAULT_SOIL_FILE = os.path.join(DATA_DIR, "soil", "ec3.soil")
SOURCE_MANIFEST = os.path.join(DATA_DIR, "SOURCE.json")


class SimulationInputError(ValueError):
    """مدخلٌ ناقص أو غير صالح لتشغيل PCSE — يُعاد 422 برمزه (لا اختلاق ولا بديل صامت)."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


def _fail(code: str, detail: str = "") -> NoReturn:
    raise SimulationInputError(code, detail)


def _number(value: Any) -> float | None:
    """رقمٌ منتهٍ أو ``None`` — لا bool ولا نصّ ولا NaN/inf (نقصٌ يُسمّى، لا يُصفَّر)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def _iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


# ── حدود PCSE 6.0.13 بوحداتها (pcse/base/weather.py: WeatherDataContainer.ranges) ──
PCSE_WEATHER_RANGES: dict[str, tuple[float, float]] = {
    "LAT": (-90.0, 90.0),
    "LON": (-180.0, 180.0),
    "ELEV": (-300.0, 6000.0),
    "IRRAD": (0.0, 40e6),
    "TMIN": (-50.0, 60.0),
    "TMAX": (-50.0, 60.0),
    "VAP": (0.06, 199.3),
    "RAIN": (0.0, 25.0),
    "WIND": (0.0, 100.0),
}
# pcse/util.py: check_angstromAB (A ∈ [0.1, 0.4] · B ∈ [0.3, 0.7] · A+B ∈ [0.6, 0.9]).
PCSE_ANGSTROM_BOUNDS = {"A": (0.1, 0.4), "B": (0.3, 0.7), "SUM": (0.6, 0.9)}
# pcse/input/sitedataproviders.py: WOFOST72SiteDataProvider._defaults["WAV"] ⇒ [0, 100] cm.
PCSE_WAV_RANGE_CM = (0.0, 100.0)

_DAY_REQUIRED = ("date", "tmin", "tmax", "rain_mm", "solar_radiation_mj_m2")
_VAPOUR_KEYS = (("vapour_pressure_hpa", 1.0), ("vapour_pressure_kpa", 10.0))  # ⇒ hPa
_WIND_KEYS = (("wind_2m_m_s", 2), ("wind_10m_m_s", 10))  # ارتفاع القياس بالمتر
_SITE_KEYS = (("latitude", "LAT"), ("longitude", "LON"), ("elevation_m", "ELEV"))


def _weather_day(i: int, day: Any) -> tuple[dict[str, Any], str, str]:
    """يومٌ واحد بوحدات PCSE + مفتاحا ضغط البخار والرياح اللذان جاء منهما."""
    if not isinstance(day, dict):
        _fail("weather_day_invalid", f"{i}:not_an_object")
    missing = [k for k in _DAY_REQUIRED if day.get(k) is None]
    vap = [(k, f) for k, f in _VAPOUR_KEYS if day.get(k) is not None]
    wind = [(k, h) for k, h in _WIND_KEYS if day.get(k) is not None]
    if not vap:
        # الرطوبة/نقطة الندى لا تُحوَّل هنا: ضغط البخار منتَجُ محرّك الطقس (ea_kpa).
        missing.append("vapour_pressure_hpa|vapour_pressure_kpa")
    if not wind:
        # wind_m_s بلا ارتفاعٍ مُعلَن: PCSE تريد 2 م، وافتراضه يُضخّم ET0 إن كان قياس 10 م.
        hint = "(wind_m_s_has_no_declared_height)" if day.get("wind_m_s") is not None else ""
        missing.append("wind_2m_m_s|wind_10m_m_s" + hint)
    if missing:
        _fail("weather_day_missing", f"{i}:" + ",".join(missing))
    if len(vap) > 1:
        _fail("weather_day_ambiguous", f"{i}:vapour_pressure")
    if len(wind) > 1:
        _fail("weather_day_ambiguous", f"{i}:wind")
    day_date = _iso_date(day["date"])
    if day_date is None:
        _fail("weather_day_invalid", f"{i}:date")
    (vap_key, vap_factor), (wind_key, wind_height) = vap[0], wind[0]
    values: dict[str, float] = {}
    for key in ("tmin", "tmax", "rain_mm", "solar_radiation_mj_m2", vap_key, wind_key):
        number = _number(day[key])
        if number is None:
            _fail("weather_day_invalid", f"{i}:{key}")
        values[key] = number
    record = {
        "DAY": day_date,
        "TMIN": values["tmin"],
        "TMAX": values["tmax"],
        "RAIN": values["rain_mm"] / 10.0,
        "IRRAD": values["solar_radiation_mj_m2"] * 1e6,
        "VAP": values[vap_key] * vap_factor,
        "WIND": values[wind_key],
    }
    source_keys = {
        "TMIN": "tmin",
        "TMAX": "tmax",
        "RAIN": "rain_mm",
        "IRRAD": "solar_radiation_mj_m2",
        "VAP": vap_key,
        "WIND": wind_key,
    }
    for pcse_key, src_key in source_keys.items():
        lo, hi = PCSE_WEATHER_RANGES[pcse_key]
        if not lo <= record[pcse_key] <= hi:
            _fail("weather_day_out_of_range", f"{i}:{src_key}")
    if record["TMIN"] > record["TMAX"]:
        _fail("weather_day_invalid", f"{i}:tmin_gt_tmax")
    record["WIND_HEIGHT_M"] = wind_height
    return record, vap_key, wind_key


def _angstrom(weather: dict[str, Any]) -> dict[str, Any]:
    a_raw, b_raw = weather.get("angstrom_a"), weather.get("angstrom_b")
    if a_raw is None and b_raw is None:
        return {"A": None, "B": None, "from": "pcse_default"}
    a, b = _number(a_raw), _number(b_raw)
    if a is None or b is None:
        _fail("weather_angstrom_invalid", "angstrom_a_and_angstrom_b_required_together")
    bounds = PCSE_ANGSTROM_BOUNDS
    if not (
        bounds["A"][0] <= abs(a) <= bounds["A"][1]
        and bounds["B"][0] <= abs(b) <= bounds["B"][1]
        and bounds["SUM"][0] <= abs(a) + abs(b) <= bounds["SUM"][1]
    ):
        _fail("weather_angstrom_invalid", f"A={a},B={b}")
    return {"A": a, "B": b, "from": "request"}


def build_weather(weather: Any) -> dict[str, Any]:
    """سلسلة يوميّة بوحدات PCSE + موقع + أنغستروم. نقصٌ/تعارض/فجوة ⇒ ``SimulationInputError``."""
    if not isinstance(weather, dict):
        _fail("weather_daily_required")
    daily = weather.get("daily")
    if not isinstance(daily, list) or not daily:
        _fail("weather_daily_required")
    missing = [k for k, _ in _SITE_KEYS if weather.get(k) is None]
    if missing:
        _fail("weather_site_missing", ",".join(missing))
    site: dict[str, float] = {}
    for key, pcse_key in _SITE_KEYS:
        number = _number(weather[key])
        lo, hi = PCSE_WEATHER_RANGES[pcse_key]
        if number is None or not lo <= number <= hi:
            _fail("weather_site_invalid", key)
        site[pcse_key] = number
    angstrom = _angstrom(weather)
    parsed = [_weather_day(i, d) for i, d in enumerate(daily)]
    days = sorted((record for record, _, _ in parsed), key=lambda r: r["DAY"])
    for prev, cur in pairwise(days):
        if cur["DAY"] == prev["DAY"]:
            _fail("weather_dates_duplicate", cur["DAY"].isoformat())
        if cur["DAY"] - prev["DAY"] != timedelta(days=1):
            # WeatherDataProvider بلا يوم ⇒ WeatherDataProviderError في منتصف الموسم (503 مُبهَم).
            _fail("weather_dates_not_contiguous", (prev["DAY"] + timedelta(days=1)).isoformat())
    return {
        "site": site,
        "angstrom": angstrom,
        "days": days,
        "first_date": days[0]["DAY"],
        "last_date": days[-1]["DAY"],
        "vapour_pressure_from": sorted({vap_key for _, vap_key, _ in parsed}),
        "wind_from": sorted({wind_key for _, _, wind_key in parsed}),
    }


# ── التربة: معاملات WaterbalanceFD (pcse/soil/classic_waterbalance.py) ──
SOIL_FIELDS: tuple[tuple[str, str], ...] = (
    ("SMFCF", "field_capacity"),  # كسر حجميّ
    ("SMW", "wilting_point"),  # كسر حجميّ
    ("SM0", "saturation"),  # كسر حجميّ
    ("CRAIRC", "critical_air_content"),  # كسر حجميّ
    ("RDMSOL", "rootable_depth_cm"),  # cm
    ("SOPE", "max_percolation_root_zone_cm_d"),  # cm/يوم
    ("KSUB", "max_percolation_subsoil_cm_d"),  # cm/يوم
)
_FRACTIONS = ("SMFCF", "SMW", "SM0", "CRAIRC")


@lru_cache(maxsize=1)
def load_default_soil(path: str = DEFAULT_SOIL_FILE) -> dict[str, Any]:
    """يقرأ القيم العدديّة المفردة ``NAME = value`` من ملفّ التربة المحزوم (صيغة CABO).

    المصدر الوحيد لأرقام التربة الافتراضيّة هو الملفّ نفسه (EC3-medium fine) — لا أرقام
    منسوخة في الشيفرة. نقصُ معاملٍ فيه عطلُ تحزيم (RuntimeError) لا خطأ مدخل.
    """
    wanted = {name for name, _ in SOIL_FIELDS}
    values: dict[str, float] = {}
    name = ""
    with open(path, encoding="ascii") as fp:
        for raw in fp:
            line = raw.split("!", 1)[0].strip()
            if not line or line.startswith("*") or "=" not in line:
                continue
            key, _, rest = line.partition("=")
            key, rest = key.strip(), rest.strip()
            if key == "SOLNAM":
                name = rest.strip("'\"")
            elif key in wanted:
                values[key] = float(rest.rstrip(","))
    absent = sorted(wanted - set(values))
    if absent:
        raise RuntimeError("default_soil_file_incomplete:" + ",".join(absent))
    return {"name": name, "file": os.path.relpath(path, DATA_DIR), "values": values}


def build_soil(soil: Any) -> dict[str, Any]:
    """معاملات تربة WaterbalanceFD: من الطلب حيث وُجدت، وإلّا من التربة الافتراضيّة **مُسمّاةً**."""
    s = soil if isinstance(soil, dict) else {}
    default = load_default_soil()
    params: dict[str, float] = {}
    origin: dict[str, str] = {}
    for pcse_key, req_key in SOIL_FIELDS:
        if s.get(req_key) is not None:
            number = _number(s[req_key])
            if number is None:
                _fail("soil_invalid", req_key)
            params[pcse_key], origin[pcse_key] = number, f"request:{req_key}"
        else:
            params[pcse_key] = default["values"][pcse_key]
            origin[pcse_key] = f"default_soil:{default['file']}"
    names = dict(SOIL_FIELDS)
    for key in _FRACTIONS:
        if not 0.0 < params[key] <= 1.0:
            _fail("soil_invalid", names[key])
    if params["RDMSOL"] < 10.0:
        # WaterbalanceFD يبدأ بطبقة جذور 10 سم (DEFAULT_RD) — عمقٌ أقلّ لا معنى له فيها.
        _fail("soil_invalid", "rootable_depth_cm")
    for key in ("SOPE", "KSUB"):
        if params[key] <= 0.0:
            _fail("soil_invalid", names[key])
    defaulted = [k for k, _ in SOIL_FIELDS if origin[k].startswith("default_soil:")]
    if not params["SMW"] < params["SMFCF"] < params["SM0"] or params["CRAIRC"] >= params["SM0"]:
        # خلطُ قيمةٍ من الطلب بأخرى افتراضيّة قد يكسر الترتيب — يُرفَض ويُسمّى المُفترَض.
        _fail(
            "soil_invalid",
            "wilting_point<field_capacity<saturation,critical_air_content<saturation"
            + (f"(defaulted:{'|'.join(defaulted)})" if defaulted else ""),
        )
    if not defaulted:
        source = "request"
    elif len(defaulted) == len(SOIL_FIELDS):
        source = "default_soil"
    else:
        source = "request+default_soil"
    return {
        "params": params,
        "origin": origin,
        "defaulted": defaulted,
        "source": source,
        "default_soil_name": default["name"],
    }


def build_site(soil: Any, soil_params: dict[str, float]) -> dict[str, Any]:
    """WAV/SMLIM لـ``WOFOST72SiteDataProvider`` (يملأ IFUNRN/NOTINF/SSI/SSMAX بافتراضات PCSE).

    ``available_water_mm`` بدلالة البديل الحتميّ نفسها: ماءٌ متاح فوق نقطة الذبول في المقطع عند
    الزراعة ⇒ ``WAV`` (cm = mm / 10). غيابه ⇒ مقطعٌ عند السعة الحقليّة ``(SMFCF−SMW)·RDMSOL``
    — افتراضٌ **مُسمّى** في ``defaults_applied``. و``SMLIM = SMFCF``: افتراض PCSE (0.4) كان
    يضع طبقة الـ10 سم الأولى فوق السعة الحقليّة فلا يعني «المقطع عند السعة الحقليّة» ما يقوله.
    """
    s = soil if isinstance(soil, dict) else {}
    if s.get("available_water_mm") is not None:
        mm = _number(s["available_water_mm"])
        if mm is None or mm < 0.0:
            _fail("soil_invalid", "available_water_mm")
        wav, wav_from = mm / 10.0, "request:available_water_mm"
    else:
        wav = (soil_params["SMFCF"] - soil_params["SMW"]) * soil_params["RDMSOL"]
        wav_from = "default:profile_at_field_capacity"
    lo, hi = PCSE_WAV_RANGE_CM
    if not lo <= wav <= hi:
        _fail("site_invalid", f"WAV={wav:g}cm_outside_{lo:g}..{hi:g}")
    return {"WAV": wav, "SMLIM": soil_params["SMFCF"], "WAV_from": wav_from}


def _irrigation(
    am: dict[str, Any], start: date, end: date
) -> tuple[list[dict[str, Any]] | None, dict[str, Any]]:
    """أحداث ريّ PCSE: ``irrigate`` بـ``{amount: cm, efficiency: كسر}`` (pcse/signals.py).

    مثال وثيقة AgroManager يكتب ``irrigation_amount``، لكنّ ``WaterbalanceFD._on_IRRIGATE``
    يقرأ ``amount``/``efficiency`` — المفتاح الخاطئ يُسقِط الإشارة بـTypeError.
    """
    events = am.get("irrigation_events")
    if events in (None, []):
        seasonal = am.get("irrigation_mm")
        if seasonal is None:
            return None, {"mode": "none_declared", "net_mm": 0.0}
        total = _number(seasonal)
        if total is None or total < 0.0:
            _fail("agromanagement_invalid", "irrigation_mm")
        if total > 0.0:
            # PCSE نموذج يوميّ: مجموعٌ موسميّ بلا تواريخ لا يوضَع في الزمن دون اختلاق جدول.
            _fail("irrigation_schedule_required", "irrigation_mm_without_dated_irrigation_events")
        return None, {"mode": "rainfed_declared", "net_mm": 0.0}
    if not isinstance(events, list):
        _fail("agromanagement_invalid", "irrigation_events")
    efficiency_all = am.get("application_efficiency")
    table: list[dict[date, dict[str, float]]] = []
    seen: set[date] = set()
    gross_mm = net_mm = 0.0
    for i, event in enumerate(events):
        if not isinstance(event, dict):
            _fail("irrigation_event_invalid", f"{i}:not_an_object")
        day = _iso_date(event.get("date"))
        if day is None:
            _fail("irrigation_event_invalid", f"{i}:date")
        depth = _number(event.get("depth_mm"))
        if depth is None or depth < 0.0:
            _fail("irrigation_event_invalid", f"{i}:depth_mm")
        efficiency = _number(event.get("efficiency", efficiency_all))
        if efficiency is None or not 0.0 < efficiency <= 1.0:
            # كفاءةٌ غائبة لا تصير 1.0 (نفس قاعدة supervisor: لا كفاءة مفترَضة).
            _fail("irrigation_event_invalid", f"{i}:efficiency")
        if not start <= day <= end:
            _fail("irrigation_event_invalid", f"{i}:date_outside_season")
        if day in seen:
            # _on_IRRIGATE يستبدل ولا يجمع: حدثان في يوم واحد ⇒ يضيع الأوّل بصمت.
            _fail("irrigation_event_invalid", f"{i}:duplicate_date")
        seen.add(day)
        table.append({day: {"amount": depth / 10.0, "efficiency": efficiency}})
        gross_mm += depth
        net_mm += depth * efficiency
    timed_events = [
        {
            "event_signal": "irrigate",
            "name": "SAHOOL irrigation events",
            "comment": "amount in cm (depth_mm / 10), efficiency as fraction",
            "events_table": table,
        }
    ]
    return timed_events, {
        "mode": "dated_events",
        "events": len(table),
        "gross_mm": round(gross_mm, 6),
        "net_mm": round(net_mm, 6),
    }


def build_agromanagement(
    agromanagement: Any,
    sim_crop: sim_crop_registry.SimCrop,
    weather_first: date,
    weather_last: date,
) -> dict[str, Any]:
    """حملة واحدة بالشكل الذي يقرؤه ``AgroManager``: ``[{date: {CropCalendar, TimedEvents, StateEvents}}]``.

    تبدأ الحملة يوم الزراعة (فيعني ``WAV`` ماءَ التربة عند الزراعة). ``harvest_date`` ⇒ نهاية
    ``earliest`` (النضج أو الحصاد أيّهما أسبق)؛ غيابه ⇒ ``maturity`` بحدٍّ أقصى هو آخر يوم طقس.
    """
    am = agromanagement if isinstance(agromanagement, dict) else {}
    if am.get("planting_date") is None:
        _fail("agromanagement_missing", "planting_date")
    start = _iso_date(am["planting_date"])
    if start is None:
        _fail("agromanagement_invalid", "planting_date")
    start_type = am.get("crop_start_type", "sowing")
    if start_type not in ("sowing", "emergence"):
        _fail("agromanagement_invalid", "crop_start_type")
    if am.get("harvest_date") is not None:
        end = _iso_date(am["harvest_date"])
        if end is None:
            _fail("agromanagement_invalid", "harvest_date")
        if end <= start:
            _fail("agromanagement_invalid", "harvest_date_not_after_planting_date")
        end_type, end_from = "earliest", "harvest_date"
    else:
        end, end_type, end_from = weather_last, "maturity", "weather_series_end"
    if am.get("max_duration_days") is not None:
        limit = _number(am["max_duration_days"])
        if limit is None or limit < 1 or limit != int(limit):
            _fail("agromanagement_invalid", "max_duration_days")
        if start + timedelta(days=int(limit)) < end:
            end, end_type, end_from = (
                start + timedelta(days=int(limit)),
                "maturity",
                "max_duration_days",
            )
    if start < weather_first or end > weather_last:
        _fail(
            "weather_does_not_cover_season",
            f"{start.isoformat()}..{end.isoformat()}_not_within_"
            f"{weather_first.isoformat()}..{weather_last.isoformat()}",
        )
    span = (end - start).days
    if span < 1:
        _fail("weather_does_not_cover_season", "season_shorter_than_one_day")
    # CropCalendar.__call__ يفحص يوم الحصاد ثمّ ``duration == max_duration`` فيكتب الثاني فوق
    # الأوّل: بحدٍّ مساوٍ للمدى يُنهى المحصول «max_duration» يوم الحصاد فلا يُسجَّل DOH.
    max_duration = span + 1 if end_type == "earliest" else span
    timed_events, irrigation = _irrigation(am, start, end)
    crop_calendar = {
        "crop_name": sim_crop.pcse_crop,
        "variety_name": sim_crop.pcse_variety,
        "crop_start_date": start,
        "crop_start_type": start_type,
        "crop_end_date": end if end_type == "earliest" else None,
        "crop_end_type": end_type,
        "max_duration": max_duration,
    }
    return {
        "agromanagement": [
            {
                start: {
                    "CropCalendar": crop_calendar,
                    "TimedEvents": timed_events,
                    "StateEvents": None,
                }
            }
        ],
        "season": {
            "start": start.isoformat(),
            "end_limit": end.isoformat(),
            "end_limit_from": end_from,
            "crop_start_type": start_type,
            "crop_end_type": end_type,
            "max_duration_days": max_duration,
        },
        "irrigation": irrigation,
    }


@dataclass(frozen=True)
class PcseRunInputs:
    """كلّ ما يلزم ``Wofost72_WLP_CWB`` بوحدات PCSE + مصدر كلّ قيمة (لا رقم بلا أصل)."""

    crop: sim_crop_registry.SimCrop
    weather: dict[str, Any]
    soil: dict[str, Any]
    site: dict[str, Any]
    agromanagement: list[dict[Any, Any]]
    season: dict[str, Any]
    irrigation: dict[str, Any]
    defaults_applied: tuple[str, ...]

    def provenance(self) -> dict[str, Any]:
        wx = self.weather
        return {
            "crop_parameters": {
                "pcse_crop": self.crop.pcse_crop,
                "pcse_variety": self.crop.pcse_variety,
                "source": self.crop.parameter_source,
                "version": self.crop.parameter_version,
            },
            "soil": {
                "source": self.soil["source"],
                "default_soil_name": self.soil["default_soil_name"],
                "parameters": {
                    k: {"value": v, "from": self.soil["origin"][k]}
                    for k, v in self.soil["params"].items()
                },
            },
            "site": {
                "WAV_cm": self.site["WAV"],
                "WAV_from": self.site["WAV_from"],
                "SMLIM": self.site["SMLIM"],
                "SMLIM_from": "soil.SMFCF",
            },
            "weather": {
                "days_supplied": len(wx["days"]),
                "first_date": wx["first_date"].isoformat(),
                "last_date": wx["last_date"].isoformat(),
                "site": dict(wx["site"]),
                "vapour_pressure_from": wx["vapour_pressure_from"],
                "wind_from": wx["wind_from"],
                "angstrom_from": wx["angstrom"]["from"],
            },
            "season": dict(self.season),
            "irrigation": dict(self.irrigation),
        }


def build_run_inputs(
    sim_crop: sim_crop_registry.SimCrop,
    weather: Any,
    soil: Any,
    agromanagement: Any,
) -> PcseRunInputs:
    """الباني الجامع: طقس ⇒ تربة ⇒ موقع ⇒ إدارة. أوّل نقص يُرفَع باسمه (422)."""
    wx = build_weather(weather)
    soil_built = build_soil(soil)
    site = build_site(soil, soil_built["params"])
    agro = build_agromanagement(agromanagement, sim_crop, wx["first_date"], wx["last_date"])
    defaults: list[str] = [f"soil.{k}" for k in soil_built["defaulted"]]
    if site["WAV_from"].startswith("default:"):
        defaults.append("site.WAV")
    if wx["angstrom"]["from"] == "pcse_default":
        defaults.append("weather.angstrom_ab")
    if agro["irrigation"]["mode"] == "none_declared":
        defaults.append("irrigation.none_declared")
    return PcseRunInputs(
        crop=sim_crop,
        weather=wx,
        soil=soil_built,
        site=site,
        agromanagement=agro["agromanagement"],
        season=agro["season"],
        irrigation=agro["irrigation"],
        defaults_applied=tuple(defaults),
    )


def vendored_source_manifest() -> dict[str, Any]:
    """``pcse_data/SOURCE.json``: مصدر كلّ ملفّ محزوم (مستودع · commit · sha256)."""
    with open(SOURCE_MANIFEST, encoding="utf-8") as fp:
        return json.load(fp)
