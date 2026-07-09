from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"


def read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_ui11_field_drawer_shell_wraps_existing_drawer_without_moving_behavior():
    shell = read("sections/maphub/FieldDrawerShell.tsx")
    assert "export function FieldDrawerShell" in shell
    assert 'data-testid="maphub-field-drawer-shell"' in shell
    assert 'data-sahool-region="field-drawer"' in shell
    assert "data-field-id" in shell
    assert "data-open" in shell
    maphub = read("sections/MapHub.tsx")
    assert "import { FieldDrawerShell } from './maphub/FieldDrawerShell';" in maphub
    assert "<FieldDrawerShell fieldId={fieldId} open={detailOpen}>" in maphub
    assert "<FieldDetailDrawer" in maphub
    assert "</FieldDrawerShell>" in maphub


def test_ui11_field_timeline_shell_wraps_imagery_timeline_and_exposes_season_context():
    shell = read("sections/maphub/FieldTimelineShell.tsx")
    assert "export function FieldTimelineShell" in shell
    assert "FieldTimelineKind" in shell
    for kind in ["imagery", "operations", "learning"]:
        assert kind in shell
    assert 'data-testid="maphub-field-timeline-shell"' in shell
    assert 'data-sahool-region="season-timeline"' in shell
    assert "data-season-id" in shell
    maphub = read("sections/MapHub.tsx")
    assert "import { FieldTimelineShell } from './maphub/FieldTimelineShell';" in maphub
    assert "<FieldTimelineShell" in maphub
    assert 'kind="imagery"' in maphub
    assert "activeSeasonId={activeSeasonId}" in maphub
    assert 'data-testid="two-year-imagery-timeline"' in maphub


def test_ui12_action_from_map_palette_exists_and_does_not_fake_writes():
    palette = read("sections/maphub/MapActionPalette.tsx")
    assert "export function MapActionPalette" in palette
    assert 'data-testid="maphub-action-from-map-palette"' in palette
    assert 'data-sahool-region="action-from-map"' in palette
    for prop in ["onPinScouting", "onOpenTimeline", "onOpenAlerts", "onAddField"]:
        assert prop in palette
    assert "disabled={!canMutate || !fieldReady}" in palette
    assert "fake" not in palette.lower()
    maphub = read("sections/MapHub.tsx")
    assert "import { MapActionPalette } from './maphub/MapActionPalette';" in maphub
    assert "<MapActionPalette" in maphub
    assert "onPinScouting={() => { setPinMode(true); setDrawTools(false); }}" in maphub
    assert "onOpenTimeline={() => setShowImageryTimeline(true)}" in maphub
    assert "onOpenAlerts={() => setShowAlerts(true)}" in maphub
    assert "onAddField={() => setShowAddField(true)}" in maphub


def test_ui13_role_aware_map_surface_contract_is_explicit():
    contract = read("sections/maphub/roleUiContract.ts")
    assert "export type SahoolUiRole" in contract
    assert "export type RoleUiCapability" in contract
    assert "roleCan" in contract
    assert "roleUiMode" in contract
    for capability in [
        "create_field",
        "mutate_field",
        "create_scouting_pin",
        "run_backfill",
        "delete_field",
    ]:
        assert capability in contract
    surface = read("sections/maphub/RoleAwareMapSurface.tsx")
    assert "export function RoleAwareMapSurface" in surface
    assert 'data-testid="maphub-role-aware-surface"' in surface
    assert 'data-sahool-region="role-aware-map-surface"' in surface
    assert "data-role-mode" in surface
    assert "data-can-create-field" in surface
    maphub = read("sections/MapHub.tsx")
    assert "import { RoleAwareMapSurface } from './maphub/RoleAwareMapSurface';" in maphub
    assert "<RoleAwareMapSurface role={user?.role}>" in maphub
    assert "</RoleAwareMapSurface>" in maphub
