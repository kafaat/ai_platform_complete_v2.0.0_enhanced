from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


WORKSPACE_DECORATORS_MOVED_FROM_FIELDS = [
    '@router.get("/api/v1/fields/{field_id}/available-dates")',
    '@router.get("/api/v1/fields/{field_id}/imagery/timeline")',
    '@router.get("/api/v1/fields/{field_id}/weather/irrigation-advice")',
    '@router.get("/api/v1/fields/{field_id}/weather/disease-risk")',
]


def test_ui28_workspace_duplicate_routes_are_removed_from_large_fields_router():
    fields = read("services/sahool-platform/api/routers/fields.py")
    for decorator in WORKSPACE_DECORATORS_MOVED_FROM_FIELDS:
        assert decorator not in fields
    assert "UI-28 route ownership: exposed by api/routers/field_workspace_imagery.py" in fields
    assert "UI-28 route ownership: exposed by api/routers/field_workspace_weather.py" in fields
    # UI-31: unified timeline is now extracted to field_workspace_timeline.py.
    assert '@router.get("/api/v1/fields/{field_id}/unified-timeline")' not in fields


def test_ui29_route_ownership_contract_lists_canonical_facade_owners():
    contract = read("services/sahool-platform/api/field_workspace_route_contract.py")
    imagery = read("services/sahool-platform/api/routers/field_workspace_imagery.py")
    weather = read("services/sahool-platform/api/routers/field_workspace_weather.py")
    priority = read("services/sahool-platform/api/routers/field_priority_queue.py")
    assert "FIELD_WORKSPACE_ROUTE_OWNERSHIP" in contract
    assert "FIELD_WORKSPACE_FIELDS_ROUTER_BUDGET" in contract
    assert "GET /api/v1/fields/{field_id}/available-dates" in contract
    assert "api.routers.field_workspace_imagery" in contract
    assert "GET /api/v1/fields/{field_id}/weather/operation-windows" in contract
    assert "api.routers.field_workspace_weather" in contract
    assert "GET /api/v1/fields/{field_id}/priority-queue" in contract
    assert "api.routers.field_priority_queue" in contract
    assert '@router.get("/api/v1/fields/{field_id}/available-dates")' in imagery
    assert '@router.get("/api/v1/fields/{field_id}/weather/irrigation-advice")' in weather
    assert '@router.get("/api/v1/fields/{field_id}/priority-queue")' in priority


def test_ui30_workspace_context_banner_and_availability_contract_are_wired():
    availability = read("frontend/src/sections/fieldWorkspaceAvailability.ts")
    banner = read("frontend/src/sections/FieldWorkspaceContextBanner.tsx")
    route = read("frontend/src/sections/FieldWorkspaceRouteShell.tsx")
    tabs = read("frontend/src/sections/FieldWorkspaceTabs.tsx")
    assert "getWorkspaceTabAvailability" in availability
    assert "listUnavailableWorkspaceTabs" in availability
    assert "يتطلب موسماً نشطاً season_id" in availability
    assert "لا يتم إنشاء موسم أو توصيات أو جداول بديلة من الواجهة" in banner
    assert (
        "FieldWorkspaceContextBanner fieldId={fieldId} seasonId={seasonId} activeTab={activeTab}"
        in route
    )
    assert "getWorkspaceTabAvailability(tab.id" in tabs
    assert "title={disabled ? availability.reason_ar : tab.label_ar}" in tabs
