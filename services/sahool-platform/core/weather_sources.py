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
        "roles": ["forecast", "historical_weather", "hourly_weather", "et0_vpd_inputs"],
        "note": "البوّابة الأساسيّة: توقّع + تاريخ (منذ 1940) + ساعيّ، بلا مفتاح.",
    },
    "nasa_power": {
        "id": "nasa_power",
        "label": "NASA POWER",
        "active": False,  # صادق: غير موصول بعد (لا استدعاء في الكود).
        "verified": True,
        "free": True,
        "auth": "none",
        "coverage_yemen": True,
        "resolution": "~0.5° (agroclimatology)",
        "roles": ["solar_radiation", "agroclimatology", "historical_weather", "et_inputs"],
        "note": "إشعاع شمسيّ + أرصاد زراعيّة-مناخيّة (مهمّ للطاقة الشمسيّة/ET) — يحتاج وصلاً.",
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
        "label": "ERA5 / ERA5-Land (Copernicus)",
        "active": False,
        "verified": True,
        "free": True,
        "auth": "cds-api (أو عبر Open-Meteo)",
        "coverage_yemen": True,
        "roles": ["climate_baseline", "historical_reanalysis"],
        "note": "خطّ أساس مناخيّ/تحليل تاريخيّ طويل — متاح جزئيّاً عبر Open-Meteo.",
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
