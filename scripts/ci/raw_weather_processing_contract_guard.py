#!/usr/bin/env python3
"""Guard the weather raw-data processing contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def main() -> int:
    raw = read("services/weather-service/raw_weather_processing.py")
    runtime = read("services/weather-service/weather_runtime.py")
    entry = read("services/weather-service/main.py")
    docker = read("services/weather-service/Dockerfile")
    checks = {
        "raw weather runtime module": "class RawWeatherProcessRequest" in raw and "build_raw_weather_response" in raw,
        "raw endpoint registered": 'app.post("/v1/weather/raw/process")' in entry,
        "raw handler in runtime": "async def raw_weather_process" in runtime,
        "raw logic not in main": "RawWeatherProcessRequest" not in entry and "build_raw_weather_response" not in entry,
        "provenance flags": "fabricated_weather" in raw and "operation_window_computed" in raw,
        "bounded processing": "max_items" in raw and "le=2000" in raw,
        "raw capability advertised": "raw_weather_processing" in runtime,
        "container copies service dir": "COPY services/weather-service/ /app/" in docker,
        "docker liveness healthz": "/healthz" in docker and "/readyz" not in docker.split("HEALTHCHECK", 1)[-1],
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        for name in failed:
            print(f"raw_weather_processing_contract_failed: {name}")
        return 1
    print("raw_weather_processing_contract_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
