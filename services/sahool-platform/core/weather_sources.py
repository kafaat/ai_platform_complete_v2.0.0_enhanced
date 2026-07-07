"""سِجِلّ مصادر الطقس (سلسلة مزوّدين صادقة، V68) — منطق صرف.

على نمط سِجِلّ مصادر الصور: كلّ مصدر يُصنَّف صراحةً، و``active=True`` **فقط** لما هو
موصول فعلاً في الكود. لا مبالغة — Open-Meteo مُستدعى فعلاً (``connectors/openmeteo.py``
+ ``field_intelligence_adapters.py``)، أمّا NASA POWER/CHIRPS/ECMWF/GFS/ERA5 فمُخطَّطة
(غير موصولة بعد) رغم أنّها مجانيّة وتغطّي اليمن.

يُغذّي لاحقاً سلسلة احتياط الطقس + عرض «مصادر الطقس» في الواجهة. نقيّ (بلا I/O).
"""

from __future__ import annotations

from typing import Any

WEATHER_SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    "open_meteo": {
        "id": "open_meteo",
        "label": "Open-Meteo",
        "active": True,  # موصول فعلاً: connectors/openmeteo.py + field_intelligence_adapters.
        "verified": True,
        "free": True,
        "auth": "none",
        "coverage_yemen": True,
        "resolution": "~9km (ERA5-based since 2017)",
        "roles": [
            "forecast",
            "historical_weather",
            "hourly_weather",
            "et0_vpd_inputs",
            "wind",  # سرعة/اتّجاه الرياح 10م — نافذة الرشّ + ET0 + تحذير الرياح/الحرارة.
            "spray_window",
        ],
        "note": (
            "البوّابة الأساسيّة: توقّع + تاريخ (منذ 1940) + ساعيّ + رياح 10م (نافذة الرشّ/"
            "ET0)، بلا مفتاح. حاجة الرياح على مستوى الحقل مُغطّاة هنا — لا حاجة لبيانات "
            "إعادة تحليل خشنة (MERRA-2/JRA-55/NCEP) أو رياح محيطيّة (ASCAT/CCMP)."
        ),
    },
    "nasa_power": {
        "id": "nasa_power",
        "label": "NASA POWER",
        "active": True,  # موصول فعلاً: connectors/nasa_power.py → /fields/{id}/wind/prevailing.
        "verified": True,
        "free": True,
        "auth": "none",
        "coverage_yemen": True,
        "resolution": "~0.5° (agroclimatology)",
        "roles": [
            "solar_radiation",
            "agroclimatology",
            "historical_weather",
            "et_inputs",
            "historical_wind",  # WD10M/WS10M → وردة رياح + توصية مصدّات (wind_geometry).
        ],
        # صدق دقيق: الموصول فعلاً دور **الرياح التاريخيّة** فقط (سائد/وردة/مصدّ)؛ بقيّة
        # الأدوار (إشعاع/أرصاد-مناخيّة/ET) مُسجَّلة لكن غير موصولة بعد.
        "active_roles": ["historical_wind"],
        "note": (
            "موصول للرياح التاريخيّة (WD10M/WS10M) عبر connectors/nasa_power.py: يغذّي "
            "الاتّجاه السائد ووردة الرياح وتوصية المصدّات. أدوار الإشعاع/الأرصاد-المناخيّة/ET "
            "مُسجَّلة وتحتاج وصلاً لاحقاً."
        ),
    },
    "chirps": {
        "id": "chirps",
        "label": "CHIRPS (UCSB/USGS)",
        "active": False,
        "verified": True,
        "free": True,
        "auth": "none",
        "coverage_yemen": True,  # 50°S–50°N ⇒ يشمل اليمن.
        "resolution": "~0.05° (1981→شبه الحاضر)",
        "roles": ["rainfall_history", "drought_monitoring", "precipitation_anomaly"],
        "note": "أمطار تاريخيّة/شبه حديثة — ممتاز للجفاف والمطر في اليمن؛ يحتاج وصلاً.",
    },
    "ecmwf_open_data": {
        "id": "ecmwf_open_data",
        "label": "ECMWF Open Data (IFS/AIFS)",
        "active": False,
        "verified": True,
        "free": True,
        "auth": "none",
        "coverage_yemen": True,
        "roles": ["medium_range_forecast", "high_quality_forecast"],
        "note": "توقّعات عالميّة عالية الجودة (real-time، مجانيّة) — احتياطيّ توقّع.",
    },
    "gfs_noaa": {
        "id": "gfs_noaa",
        "label": "GFS / NOAA",
        "active": False,
        "verified": True,
        "free": True,
        "auth": "none",
        "coverage_yemen": True,
        "roles": ["forecast_fallback"],
        "note": "توقّع عالميّ بديل — احتياطيّ في السلسلة.",
    },
    "era5": {
        "id": "era5",
        "label": "ERA5 (Copernicus)",
        "active": False,
        "verified": True,
        "free": True,
        "auth": "cds-api (أو عبر Open-Meteo)",
        "coverage_yemen": True,
        "resolution": "0.25° (~25–31km) — تصحيح: ليست 500م؛ مقياس منطقة/محافظة لا نقطة حقل.",
        "roles": ["climate_baseline", "historical_reanalysis", "wind_climate", "long_history"],
        "note": (
            "خطّ أساس مناخيّ/تحليل تاريخيّ طويل (بما فيه رياح الإعادة-تحليل) — متاح جزئيّاً "
            "عبر Open-Meteo. مقياس منطقة/محافظة؛ للدقّة الحقليّة يحتاج downscaling/دمج DEM."
        ),
    },
    "era5_land": {
        "id": "era5_land",
        "label": "ERA5-Land (Copernicus)",
        "active": False,
        "verified": True,
        "free": True,
        "auth": "cds-api (أو عبر Open-Meteo)",
        "coverage_yemen": True,
        "resolution": "0.1° (~9km) — أدقّ من ERA5 للأرض/الزراعة (لا 500م).",
        "roles": [
            "historical_wind",
            "climate_baseline",
            "agroclimate",
            "soil_moisture",
            "drought",
        ],
        # أسماء CDS الرسميّة (volumetric_soil_water_layer_1..4) → أسماء ساهول + الوحدة.
        # صدق: لا أسماء MirrorEarth غير الموثّقة؛ soil_moisture_index مؤشّر مُشتقّ نحسبه.
        # حدود العمق (سم) مصدرها الوحيد هنا — تشتقّها دالّة منطقة الجذر لا أرقام مُثبَّتة.
        "soil_moisture_layers": {
            "soil_moisture_0_7cm": {
                "provider_variable": "volumetric_soil_water_layer_1",
                "unit": "m3/m3",
                "depth_top_cm": 0,
                "depth_bottom_cm": 7,
            },
            "soil_moisture_7_28cm": {
                "provider_variable": "volumetric_soil_water_layer_2",
                "unit": "m3/m3",
                "depth_top_cm": 7,
                "depth_bottom_cm": 28,
            },
            "soil_moisture_28_100cm": {
                "provider_variable": "volumetric_soil_water_layer_3",
                "unit": "m3/m3",
                "depth_top_cm": 28,
                "depth_bottom_cm": 100,
            },
            "soil_moisture_100_289cm": {  # العمق الرابع 289سم (لا 255).
                "provider_variable": "volumetric_soil_water_layer_4",
                "unit": "m3/m3",
                "depth_top_cm": 100,
                "depth_bottom_cm": 289,
            },
        },
        "derived_variables": [
            "root_zone_soil_moisture",
            "soil_moisture_percentile",
            "drought_anomaly",
        ],
        "limitations": [
            "modelled_not_in_situ",  # رطوبة نموذجيّة لا قياس حساس داخل الحقل.
            "too_coarse_for_small_field_without_downscaling",  # 9كم لا يرى المدرّجات.
            "validate_with_local_sensors_or_farmer_records",
        ],
        "note": (
            "أدقّ من ERA5 (9كم)؛ رطوبة تربة/جفاف تاريخيّ بمقياس منطقة. أسماء المتغيّرات "
            "الرسميّة من CDS (volumetric_soil_water_layer_1..4) لا أسماء MirrorEarth. يحتاج وصلاً."
        ),
    },
    "global_wind_atlas": {
        "id": "global_wind_atlas",
        "label": "Global Wind Atlas",
        "active": False,
        "verified": True,
        "free": True,
        "auth": "none",
        "coverage_yemen": True,  # صفحة مخصّصة لليمن.
        "resolution": "~250m (أطلس رياح للطاقة، لا توقّع يوميّ)",
        "roles": ["wind_energy_siting", "long_term_wind_resource"],
        "note": "أطلس رياح عالي الدقّة لتحديد مواقع طاقة الرياح/الآبار — مرجع طاقة لا forecast.",
    },
    "merra2": {
        "id": "merra2",
        "label": "MERRA-2 (NASA)",
        "active": False,
        "verified": True,
        "free": True,
        "auth": "earthdata-login",
        "coverage_yemen": True,
        "resolution": "~50km",
        "roles": ["climate_reference", "renewable_energy_reference"],
        "note": "مرجع مناخيّ/طاقة ثانويّ (~50كم) — خشن للحقل، مفيد للمقارنة.",
    },
    "ascat": {
        "id": "ascat",
        "label": "ASCAT (EUMETSAT scatterometer)",
        "active": False,
        "verified": True,
        "free": True,
        "auth": "none",
        "coverage_yemen": True,  # يغطّي سواحل/بحار اليمن (رياح سطح البحر).
        "coverage_scope": "coastal_marine",  # صدق: رياح محيطيّة، ضعيف للزراعة الداخليّة.
        "resolution": "12.5–25km",
        "roles": ["marine_wind", "coastal_wind_reference"],
        "note": "رياح سطح البحر (سواحل/بحار اليمن) — للملاحة/السواحل لا لحقول الداخل.",
    },
}


def active_weather_sources() -> list[str]:
    """مصادر الطقس الموصولة فعلاً (active=True) — صدق لا طموح."""
    return [k for k, v in WEATHER_SOURCE_REGISTRY.items() if v.get("active")]


def planned_weather_sources() -> list[str]:
    """مصادر الطقس المُسجَّلة غير الموصولة بعد (active=False)."""
    return [k for k, v in WEATHER_SOURCE_REGISTRY.items() if not v.get("active")]


def weather_sources_for_role(role: str) -> list[str]:
    """مصادر الطقس التي تخدم دوراً مُعيَّناً (forecast/rainfall_history/…)."""
    return [k for k, v in WEATHER_SOURCE_REGISTRY.items() if role in (v.get("roles") or [])]


# ── سلسلة مزوّدي ET0 (المرجع evapotranspiration) — الأساسيّ الموصول ثمّ الاحتياطيّ ──
ET0_PROVIDER_CHAIN: dict[str, Any] = {
    "primary": "open_meteo",  # موصول (نشط) — ET0 مرجعيّ + مدخلاته.
    "secondary": "nasa_power",  # مُخطَّط (إشعاع/أرصاد زراعيّة).
    "fallback": "era5_land_derived",  # مُشتقّ من ERA5-Land عند الحاجة.
    "variables": [
        "et0_reference_evapotranspiration",
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "shortwave_radiation",
        "vapour_pressure_deficit",
    ],
}


def soil_moisture_drought_class(
    current: Any, history: Any, *, min_history: int = 10
) -> dict[str, Any]:
    """صنف الجفاف من **مئينيّة رطوبة التربة المحلّيّة** — لا عتبة SMI ثابتة لكلّ اليمن.

    **صدق:** الجفاف يُقاس كمئينيّة قيمة اليوم مقابل تاريخ نفس الموقع/الموسم (الجوف/تهامة/
    إب/حضرموت/صعدة مناخات وترب مختلفة). تاريخ غير كافٍ ⇒ ``unknown`` (لا تخمين).
    العتبات: <10 شديد · 10–20 متوسّط · 20–30 بداية إجهاد · ≥30 طبيعيّ.
    """

    def _num(v: Any) -> float | None:
        if isinstance(v, bool):
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if f == f else None

    cur = _num(current)
    vals = [x for x in (_num(v) for v in (history or [])) if x is not None]
    if cur is None or len(vals) < min_history:
        return {"class": "unknown", "reason": "insufficient_history", "percentile": None}
    below = sum(1 for v in vals if v < cur)
    pct = round(100.0 * below / len(vals), 1)
    if pct < 10:
        cls = "severe_drought"
    elif pct < 20:
        cls = "moderate_drought"
    elif pct < 30:
        cls = "stress_onset"
    else:
        cls = "normal"
    return {"class": cls, "percentile": pct, "reason": None, "n_history": len(vals)}


def root_zone_soil_moisture(
    layer_values: Any, root_depth_cm: Any, *, source: str = "era5_land"
) -> dict[str, Any]:
    """رطوبة منطقة الجذر — متوسّط طبقات ERA5-Land موزوناً بسُمك التداخل مع [0, عمق الجذر].

    **صدق:** الأعماق من ``soil_moisture_layers`` (مصدر واحد) لا أرقام مُثبَّتة؛ الطبقات
    الغائبة/غير الرقميّة تُسقَط ووزنها معها. لا مدخل صالح ⇒ ``value=None`` + سبب (لا اختلاق).
    ``layer_values`` قاموس مفتاحه اسم طبقة ساهول (soil_moisture_0_7cm…) وقيمته رطوبة حجميّة
    m3/m3. يخدم قرار الريّ حسب المحصول (قمح/خضار سطحيّ 0–28سم؛ نخيل/عنب عميق 28–289سم).
    """

    def _num(v: Any) -> float | None:
        if isinstance(v, bool):
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if f == f else None

    depth = _num(root_depth_cm)
    if depth is None or depth <= 0:
        return {"value": None, "unit": "m3/m3", "reason": "invalid_root_depth", "layers_used": []}
    if not isinstance(layer_values, dict) or not layer_values:
        return {"value": None, "unit": "m3/m3", "reason": "no_layer_values", "layers_used": []}

    specs = WEATHER_SOURCE_REGISTRY.get(source, {}).get("soil_moisture_layers") or {}
    num = 0.0
    weight = 0.0
    used: list[str] = []
    for name, spec in specs.items():
        top = _num(spec.get("depth_top_cm"))
        bottom = _num(spec.get("depth_bottom_cm"))
        val = _num(layer_values.get(name))
        if top is None or bottom is None or val is None:
            continue
        overlap = min(bottom, depth) - top  # سُمك تداخل الطبقة مع منطقة الجذر (سم).
        if overlap <= 0:
            continue
        num += val * overlap
        weight += overlap
        used.append(name)

    if weight <= 0:
        return {
            "value": None,
            "unit": "m3/m3",
            "reason": "no_overlapping_layers",
            "layers_used": [],
        }
    return {
        "value": round(num / weight, 4),
        "unit": "m3/m3",
        "reason": None,
        "root_depth_cm": depth,
        "layers_used": used,
    }
