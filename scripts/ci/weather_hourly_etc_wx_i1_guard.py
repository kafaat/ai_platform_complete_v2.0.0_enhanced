#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
checks = {
    "hourly product": ROOT / "services/weather-service/hourly_etc.py",
    "provider fetch": ROOT / "services/weather-service/open_meteo.py",
    "weather route": ROOT / "services/weather-service/main.py",
    "platform client": ROOT / "services/sahool-platform/api/weather_service_client.py",
    "runtime consumer": ROOT / "services/sahool-platform/api/irrigation_runtime_orchestrator.py",
}
missing = [name for name, path in checks.items() if not path.exists()]
if missing:
    raise SystemExit("WX-I1 guard failed; missing: " + ", ".join(missing))

hourly = checks["hourly product"].read_text(encoding="utf-8")
provider = checks["provider fetch"].read_text(encoding="utf-8")
route = checks["weather route"].read_text(encoding="utf-8")
client = checks["platform client"].read_text(encoding="utf-8")
consumer = checks["runtime consumer"].read_text(encoding="utf-8")

required = [
    ("provider-native ET0 variable", "et0_fao_evapotranspiration" in provider),
    ("UTC provider request", '"timezone": "UTC"' in provider),
    ("canonical route", "/v1/weather/agro/etc/hourly" in route),
    ("content digest", "content_digest" in hourly),
    ("effective rainfall", "effective_rain_mm" in hourly),
    ("no local ET0 fallback", "penman_monteith" not in hourly and "hargreaves" not in hourly),
    ("platform client", "get_hourly_etc_product" in client),
    ("M3 consumer", "hourly_weather_product_digest" in consumer),
    ("old disaggregation removed", "DAILY_ETC_TEMPORALLY_DISAGGREGATED" not in consumer),
]
failed = [name for name, ok in required if not ok]
if failed:
    raise SystemExit("WX-I1 guard failed: " + ", ".join(failed))
print("WX-I1 native hourly ETc guard: PASS")
