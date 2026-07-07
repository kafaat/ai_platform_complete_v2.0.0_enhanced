#!/usr/bin/env python3
"""Static governance gate for public Weather/Auth-boundary routes.

The public weather endpoints are intentionally unauthenticated for map probes and
location-based calculators. This gate keeps that contract safe by requiring:
- internal FastAPI rate limiting on provider-facing public endpoints;
- explicit client-only field references for public action recommendations;
- no frontend usage of the deprecated ``field_id`` query parameter;
- a public route taxonomy file covering sensitive public GET routes.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    p = ROOT / path
    if not p.exists():
        print(f"❌ missing required file: {path}")
        sys.exit(1)
    return p.read_text(encoding="utf-8")


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        print(f"❌ missing {label}: {needle}")
        sys.exit(1)


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        print(f"❌ forbidden {label}: {needle}")
        sys.exit(1)


def main() -> int:
    weather = read("services/sahool-platform/api/routers/weather.py")
    popup = read("frontend/src/components/maphub/weather/WeatherProbePopup.ts")
    taxonomy_raw = read("services/sahool-platform/tests/_public_read_taxonomy.json")
    taxonomy = json.loads(taxonomy_raw)

    required_rate_decorators = {
        "current": '@router.get("/api/v1/weather/current", dependencies=[Depends(_rate_dependency("current"))])',
        "forecast": '@router.get("/api/v1/weather/forecast", dependencies=[Depends(_rate_dependency("forecast"))])',
        "historical": '@router.get("/api/v1/weather/historical", dependencies=[Depends(_rate_dependency("historical"))])',
        "action": 'dependencies=[Depends(_rate_dependency("weather-action-recommendation"))]',
    }
    for label, needle in required_rate_decorators.items():
        require(weather, needle, f"weather {label} rate dependency")

    for endpoint in ('"current":', '"forecast":', '"historical":'):
        require(weather, endpoint, f"explicit rate-limit bucket {endpoint}")

    require(weather, "client_field_ref", "client-only field reference parameter")
    require(weather, "deprecated=True", "deprecated field_id alias marker")
    require(
        weather, "field_ref_is_authoritative", "non-authoritative field reference response marker"
    )
    require(weather, "must not dereference", "public endpoint non-dereference warning")
    require(popup, "client_field_ref=", "frontend uses client_field_ref")
    forbid(popup, "field_id=${encodeURIComponent(fieldId)}", "frontend deprecated field_id query")

    sensitive = taxonomy.get("sensitive_public_reads", {})
    for path in [
        "/api/v1/weather/current",
        "/api/v1/weather/forecast",
        "/api/v1/weather/historical",
        "/api/v1/weather/action-recommendation",
        "/api/v1/geo-locate/field",
        "/api/v1/geo-locate/recommend",
    ]:
        if path not in sensitive:
            print(f"❌ missing public-read taxonomy entry: {path}")
            sys.exit(1)
        entry = sensitive[path]
        if not entry.get("category") or not entry.get("owner") or not entry.get("contract"):
            print(f"❌ incomplete taxonomy entry for {path}")
            sys.exit(1)

    # Guard against future public weather action code accidentally reading tenant tables.
    action_match = re.search(
        r"async def weather_action_recommendation\([\s\S]+?\n\n@router\.", weather
    )
    action_body = action_match.group(0) if action_match else ""
    forbidden_db_terms = [
        "tenant_connection",
        "SELECT ",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        " FROM fields",
        " FROM farms",
    ]
    for term in forbidden_db_terms:
        if term in action_body:
            print(f"❌ public action-recommendation appears to dereference DB/tenant data: {term}")
            sys.exit(1)

    print("public-weather-route-governance contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
