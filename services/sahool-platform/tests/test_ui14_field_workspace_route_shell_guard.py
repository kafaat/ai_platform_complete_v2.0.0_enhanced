from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_field_workspace_route_shell_exists_and_is_context_bound():
    src = read(FRONTEND / "sections" / "FieldWorkspaceRouteShell.tsx")
    assert "useParams" in src
    assert "fieldId" in src
    assert "season_id" in src
    assert "field_id + season_id" not in src.lower() or "seasonId" in src
    assert "لا تعرض أرقاماً" in src or "لا يعرض أرقاماً" in src or "لا تعرض أرقام" in src


def test_field_workspace_tabs_contract_is_explicit():
    contract = read(FRONTEND / "sections" / "fieldWorkspaceContract.ts")
    for tab in [
        "overview",
        "map",
        "season",
        "imagery",
        "weather",
        "irrigation",
        "operations",
        "recommendations",
        "reports",
    ]:
        assert tab in contract
    assert "requires_season" in contract
    assert "degraded_safe" in contract


def test_app_routes_dynamic_field_workspace_without_breaking_compat_page():
    app = read(FRONTEND / "App.tsx")
    assert "FieldWorkspaceRouteShell" in app
    assert 'path="/fields/:fieldId/workspace"' in app
    assert "case 'field-workspace': return <FieldWorkspaceRouteShell />" in app
    # Compatibility card remains imported because the route shell reuses it rather than rewriting map behavior.
    assert "./sections/FieldWorkspaceMapCard" in app


def test_field_workspace_tabs_disable_season_bound_tabs_without_season():
    tabs = read(FRONTEND / "sections" / "FieldWorkspaceTabs.tsx")
    assert "requires_season && !seasonId" in tabs
    assert "يتطلب موسماً نشطاً" in tabs
    assert "aria-current" in tabs


def test_workspace_shell_uses_existing_map_card_not_fake_panels_for_map():
    shell = read(FRONTEND / "sections" / "FieldWorkspaceRouteShell.tsx")
    assert "<FieldWorkspaceMapCard fieldId={fieldId} showPicker={false}" in shell
    assert "لا يوجد حقل نشط" in shell
    assert "PlaceholderPanel" not in shell
    assert "FieldWorkspaceImageryPanel" in shell
    assert "FieldWorkspaceWeatherPanel" in shell
    assert "FieldWorkspaceIrrigationPanel" in shell
