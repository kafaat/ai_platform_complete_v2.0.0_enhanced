#!/usr/bin/env python3
"""Field Workspace production closure gate.

This is intentionally runtime-oriented: it imports the FastAPI app, verifies that
Field Workspace routes are registered exactly once, and checks the frontend/API
contract files needed by the closed UI-5→UI-35 line.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "services" / "sahool-platform"
sys.path.insert(0, str(PLATFORM))
sys.path.insert(0, str(ROOT))

FIELD_WORKSPACE_ROUTES = {
    "GET /api/v1/fields/{field_id}/available-dates",
    "GET /api/v1/fields/{field_id}/imagery/timeline",
    "GET /api/v1/fields/{field_id}/weather/operation-windows",
    "GET /api/v1/fields/{field_id}/weather/irrigation-advice",
    "GET /api/v1/fields/{field_id}/weather/disease-risk",
    "GET /api/v1/fields/{field_id}/priority-queue",
    "GET /api/v1/farms/{farm_id}/priority-queue",
    "GET /api/v1/fields/{field_id}/unified-timeline",
}

REQUIRED_FRONTEND = [
    "frontend/src/sections/FieldWorkspaceRouteShell.tsx",
    "frontend/src/sections/FieldWorkspaceTabs.tsx",
    "frontend/src/sections/FieldWorkspaceContextBanner.tsx",
    "frontend/src/sections/FieldWorkspaceDataPanels.tsx",
    "frontend/src/sections/FieldWorkspaceTimelinePanel.tsx",
    "frontend/src/sections/FieldWorkspaceOperationsPanel.tsx",
    "frontend/src/sections/FieldWorkspaceImageryPanel.tsx",
    "frontend/src/sections/FieldWorkspaceWeatherPanel.tsx",
    "frontend/src/sections/FieldWorkspaceIrrigationPanel.tsx",
    "frontend/src/sections/fieldWorkspaceAvailability.ts",
    "frontend/src/sections/fieldWorkspaceCompletionContract.ts",
    "frontend/src/services/api/fieldTimeline.ts",
    "frontend/src/services/api/fieldImagery.ts",
    "frontend/src/services/api/fieldWeather.ts",
    "frontend/src/services/api/fieldIrrigation.ts",
    "frontend/src/services/api/fieldTasks.ts",
    "frontend/tsconfig.field-workspace-contract.json",
]

REQUIRED_BACKEND = [
    "services/sahool-platform/api/routers/field_workspace_imagery.py",
    "services/sahool-platform/api/routers/field_workspace_weather.py",
    "services/sahool-platform/api/routers/field_workspace_timeline.py",
    "services/sahool-platform/api/routers/field_priority_queue.py",
    "services/sahool-platform/api/field_workspace_route_contract.py",
    "services/sahool-platform/api/field_workspace_completion_contract.py",
]

FORBIDDEN_UI_FABRICATION = [
    ("FieldWorkspaceTimelinePanel.tsx", r"mock|demo|sample|fake"),
    ("FieldWorkspaceRecommendationsPanel.tsx", r"mock|demo|sample|fake"),
    ("FieldWorkspaceReportsPanel.tsx", r"mock|demo|sample|fake"),
    ("FieldWorkspaceIrrigationPanel.tsx", r"mock|demo|sample|fake"),
]


def fail(message: str) -> None:
    print(f"❌ {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"✓ {message}")


def check_files() -> None:
    missing = [p for p in REQUIRED_FRONTEND + REQUIRED_BACKEND if not (ROOT / p).exists()]
    if missing:
        fail("Missing Field Workspace closure files:\n" + "\n".join(missing))
    ok("Field Workspace frontend/backend closure files exist")


def check_runtime_routes() -> None:
    from api.main import app

    seen: list[tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in methods:
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                seen.append((method, path))

    route_strings = {f"{method} {path}" for method, path in seen}
    missing = sorted(FIELD_WORKSPACE_ROUTES - route_strings)
    if missing:
        fail("Missing runtime Field Workspace routes:\n" + "\n".join(missing))

    duplicates = [f"{m} {p}" for (m, p), count in Counter(seen).items() if count > 1]
    if duplicates:
        fail(
            "Duplicate runtime HTTP method/path registrations found:\n" + "\n".join(duplicates[:50])
        )

    ok("Field Workspace routes are registered once at FastAPI runtime")


def check_openapi() -> None:
    from api.main import app

    schema = app.openapi()
    paths = schema.get("paths", {})
    for route in FIELD_WORKSPACE_ROUTES:
        method, path = route.split(" ", 1)
        if path not in paths or method.lower() not in paths[path]:
            fail(f"OpenAPI missing {route}")
    ok("OpenAPI exposes all Field Workspace route contracts")


def check_fields_router_budget() -> None:
    fields_py = ROOT / "services/sahool-platform/api/routers/fields.py"
    text = fields_py.read_text(encoding="utf-8")
    forbidden_paths = [
        "/api/v1/fields/{field_id}/available-dates",
        "/api/v1/fields/{field_id}/imagery/timeline",
        "/api/v1/fields/{field_id}/weather/operation-windows",
        "/api/v1/fields/{field_id}/weather/irrigation-advice",
        "/api/v1/fields/{field_id}/weather/disease-risk",
        "/api/v1/fields/{field_id}/unified-timeline",
    ]
    for path in forbidden_paths:
        if re.search(r"@router\.get\(\s*['\"]" + re.escape(path), text):
            fail(f"fields.py reintroduced a Field Workspace decorator: {path}")
    ok("fields.py does not own specialized Field Workspace routes")


def check_frontend_contracts() -> None:
    pkg = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    scripts = pkg.get("scripts", {})
    for name in ["build", "typecheck:field-workspace-contract"]:
        if name not in scripts:
            fail(f"frontend/package.json missing script: {name}")

    for filename, pattern in FORBIDDEN_UI_FABRICATION:
        text = (ROOT / "frontend/src/sections" / filename).read_text(encoding="utf-8").lower()
        if re.search(pattern, text):
            fail(f"Potential fabricated data marker found in {filename}: {pattern}")

    weather_api = (ROOT / "frontend/src/services/api/fieldWeather.ts").read_text(encoding="utf-8")
    if "lat" in weather_api.lower() or "lon" in weather_api.lower():
        fail(
            "fieldWeather.ts must not send lat/lon; backend derives location from field_id + tenant"
        )

    ok("Frontend Field Workspace contracts are production-closure safe")


def main() -> None:
    check_files()
    check_runtime_routes()
    check_openapi()
    check_fields_router_budget()
    check_frontend_contracts()
    ok("Field Workspace production closure gate passed")


if __name__ == "__main__":
    main()
