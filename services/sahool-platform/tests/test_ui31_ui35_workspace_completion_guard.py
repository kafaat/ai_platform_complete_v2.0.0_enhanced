from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_ui31_unified_timeline_has_backend_facade_and_fields_no_longer_owns_route():
    facade = read("services/sahool-platform/api/routers/field_workspace_timeline.py")
    fields = read("services/sahool-platform/api/routers/fields.py")
    contract = read("services/sahool-platform/api/field_workspace_route_contract.py")

    assert '@router.get("/api/v1/fields/{field_id}/unified-timeline")' in facade
    assert "assemble_timeline" in facade
    assert "_assert_field_in_tenant" in facade
    assert "require_permission(Permission.FIELD_VIEW)" in facade
    assert '@router.get("/api/v1/fields/{field_id}/unified-timeline")' not in fields
    assert "api.routers.field_workspace_timeline" in contract
    assert '"allowed_workspace_routes": []' in contract


def test_ui32_frontend_timeline_domain_module_is_used():
    module = read("frontend/src/services/api/fieldTimeline.ts")
    panel = read("frontend/src/sections/FieldWorkspaceTimelinePanel.tsx")
    facade = read("frontend/src/services/api.ts")

    assert "getFieldUnifiedTimeline" in module
    assert "season_id?: string | null" in module
    assert "from '../services/api/fieldTimeline'" in panel
    assert "season_id: seasonId ?? undefined" in panel
    assert "export * from './api/fieldTimeline';" in facade


def test_ui33_no_workspace_route_duplication_in_fields_router():
    fields = read("services/sahool-platform/api/routers/fields.py")
    forbidden = [
        '@router.get("/api/v1/fields/{field_id}/available-dates")',
        '@router.get("/api/v1/fields/{field_id}/imagery/timeline")',
        '@router.get("/api/v1/fields/{field_id}/weather/irrigation-advice")',
        '@router.get("/api/v1/fields/{field_id}/weather/disease-risk")',
        '@router.get("/api/v1/fields/{field_id}/unified-timeline")',
    ]
    for marker in forbidden:
        assert marker not in fields


def test_ui34_completion_contract_exists_on_frontend_and_backend():
    frontend = read("frontend/src/sections/fieldWorkspaceCompletionContract.ts")
    backend = read("services/sahool-platform/api/field_workspace_completion_contract.py")
    for token in [
        "field_id",
        "season_id",
        "unified-timeline",
        "priority-queue",
        "imagery/timeline",
        "irrigation-advice",
    ]:
        assert token in frontend
        assert token in backend
    assert "noFrontendFabrication" in frontend
    assert "no_frontend_fabrication" in backend


def test_ui35_final_workspace_surface_is_not_placeholder_driven():
    route_shell = read("frontend/src/sections/FieldWorkspaceRouteShell.tsx")
    assert "FieldWorkspaceImageryPanel" in route_shell
    assert "FieldWorkspaceWeatherPanel" in route_shell
    assert "FieldWorkspaceIrrigationPanel" in route_shell
    assert "FieldWorkspaceOperationsPanel" in route_shell
    assert "FieldWorkspaceRecommendationsPanel" in route_shell
    assert "FieldWorkspaceReportsPanel" in route_shell
    assert "PlaceholderPanel" not in route_shell
