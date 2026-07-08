from __future__ import annotations

from math import atan, degrees, pi, sinh
from typing import Any

ALLOWED_TIMES = {"now", "+1h", "+3h", "+6h", "+12h", "+24h", "+48h"}
ALLOWED_MODELS = {"best_match", "auto", "gfs_seamless", "ecmwf_ifs04"}
ALLOWED_LAYERS = {
    "temperature",
    "wind",
    "precipitation",
    "et0",
    "vpd",
    "soil_temperature",
    "soil_temperature_10_40cm",
    "spraying_drift_risk",
    "soil_trafficability",
    "heat_stress",
    "soil_moisture",
    "pressure",
    "clouds",
}


def validate_time_model(time: str, model: str) -> tuple[str, str]:
    time = (time or "now").strip()
    model = (model or "best_match").strip()
    if time not in ALLOWED_TIMES:
        time = "now"
    if model not in ALLOWED_MODELS:
        model = "best_match"
    return time, model


def time_key_from_hour(hour: int) -> str:
    return "now" if hour <= 0 else f"+{hour}h"


def parse_series_hours(hours: str) -> list[int]:
    values: list[int] = []
    for part in (hours or "0,1,3,6,12,24,48").split(","):
        try:
            h = int(part.strip())
        except ValueError:
            continue
        if h in {0, 1, 3, 6, 12, 24, 48}:
            values.append(h)
    return values or [0, 1, 3, 6, 12, 24, 48]


def tile_lon(x: int, z: int) -> float:
    return x / (2**z) * 360.0 - 180.0


def tile_lat(y: int, z: int) -> float:
    n = pi - 2.0 * pi * y / (2**z)
    return degrees(atan(sinh(n)))


def tile_center(z: int, x: int, y: int) -> tuple[float, float]:
    west = tile_lon(x, z)
    east = tile_lon(x + 1, z)
    north = tile_lat(y, z)
    south = tile_lat(y + 1, z)
    return (north + south) / 2.0, (west + east) / 2.0


def tile_interpolation_points(z: int, x: int, y: int) -> list[dict[str, float]]:
    west = tile_lon(x, z)
    east = tile_lon(x + 1, z)
    north = tile_lat(y, z)
    south = tile_lat(y + 1, z)
    lon25 = west + (east - west) * 0.25
    lon50 = west + (east - west) * 0.50
    lon75 = west + (east - west) * 0.75
    lat25 = south + (north - south) * 0.25
    lat50 = south + (north - south) * 0.50
    lat75 = south + (north - south) * 0.75
    return [
        {"name": "nw", "lat": lat75, "lon": lon25},
        {"name": "ne", "lat": lat75, "lon": lon75},
        {"name": "sw", "lat": lat25, "lon": lon25},
        {"name": "se", "lat": lat25, "lon": lon75},
        {"name": "center", "lat": lat50, "lon": lon50},
    ]


def _num(sample: dict[str, Any], key: str, default: float | None = None) -> float | None:
    try:
        return float(sample.get(key))
    except (TypeError, ValueError):
        return default


def _ramp(value: float, low: float, high: float) -> float:
    if value <= low:
        return 0.0
    if value >= high:
        return 1.0
    return (value - low) / (high - low)


def derived_layer_value(layer: str, sample: dict[str, Any]) -> Any:
    if layer == "temperature":
        return sample.get("temperature_c")
    if layer == "wind":
        return sample.get("wind_speed_10m_kmh")
    if layer == "precipitation":
        return sample.get("precipitation_mm")
    if layer == "et0":
        return sample.get("et0_mm")
    if layer == "vpd":
        return sample.get("vpd_kpa")
    if layer == "soil_temperature":
        return sample.get("soil_temperature_6cm_c")
    if layer == "soil_temperature_10_40cm":
        vals = [
            _num(sample, "soil_temperature_18cm_c"),
            _num(sample, "soil_temperature_54cm_c"),
        ]
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else sample.get("soil_temperature_6cm_c")
    if layer == "soil_moisture":
        return sample.get("soil_moisture_1_to_3cm_m3m3")
    if layer == "pressure":
        return sample.get("surface_pressure_hpa")
    if layer == "clouds":
        return sample.get("cloud_cover_pct")
    if layer == "spraying_drift_risk":
        wind = _num(sample, "wind_speed_10m_kmh", 0.0) or 0.0
        gust = _num(sample, "wind_gusts_10m_kmh", wind) or wind
        vpd = _num(sample, "vpd_kpa", 1.0) or 1.0
        return round(
            min(1.0, _ramp(wind, 6, 22) * 0.5 + _ramp(gust, 12, 32) * 0.3 + _ramp(vpd, 2, 5) * 0.2),
            3,
        )
    if layer == "soil_trafficability":
        moisture = _num(sample, "soil_moisture_1_to_3cm_m3m3", None)
        if moisture is None:
            return None
        return round(max(0.0, min(1.0, 1.0 - _ramp(moisture, 0.22, 0.42))), 3)
    if layer == "heat_stress":
        temp = _num(sample, "temperature_c", 0.0) or 0.0
        return round(_ramp(temp, 30, 42), 3)
    return None


def unit_for_layer(layer: str) -> str:
    return {
        "temperature": "°C",
        "wind": "km/h",
        "precipitation": "mm",
        "et0": "mm",
        "vpd": "kPa",
        "soil_temperature": "°C",
        "soil_temperature_10_40cm": "°C",
        "spraying_drift_risk": "0..1",
        "soil_trafficability": "0..1",
        "heat_stress": "0..1",
        "soil_moisture": "m³/m³",
        "pressure": "hPa",
        "clouds": "%",
    }.get(layer, "")
