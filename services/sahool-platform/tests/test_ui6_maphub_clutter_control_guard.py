from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAPHUB = ROOT / "frontend/src/sections/MapHub.tsx"
OVERLAYS = ROOT / "frontend/src/sections/maphub/OperationalOverlayControls.tsx"
CLUTTER = ROOT / "frontend/src/sections/maphub/mapClutterControl.ts"


def test_maphub_clutter_control_contract_exists():
    text = CLUTTER.read_text(encoding="utf-8")
    assert "OperationalOverlayId" in text
    assert "MAPHUB_OPERATIONAL_OVERLAY_LIMIT = 3" in text
    assert "countActiveOperationalOverlays" in text
    assert "isOperationalOverlayBlocked" in text
    assert "mapClutterBlockedTitle" in text
    for layer in ["weather", "alerts", "devices", "equipment", "tasks"]:
        assert layer in text


def test_maphub_applies_operational_overlay_limit_to_heavy_live_layers():
    maphub = MAPHUB.read_text(encoding="utf-8")
    overlay_controls = OVERLAYS.read_text(encoding="utf-8")
    assert "from './maphub/mapClutterControl'" in maphub
    assert "operationalOverlayState" in maphub
    assert "isOverlayBlocked" in maphub
    assert "overlayBlockedTitle" in maphub
    assert "<OperationalOverlayControls" in maphub
    for layer in ["weather", "alerts", "devices", "equipment", "tasks"]:
        assert f"disabled={{props.isOverlayBlocked('{layer}')}}" in overlay_controls
        assert f"title={{props.overlayBlockedTitle('{layer}')}}" in overlay_controls


def test_maphub_does_not_limit_contextual_layers_with_same_rule():
    text = OVERLAYS.read_text(encoding="utf-8")
    # Contextual/non-live layers remain independently controlled in this phase.
    for testid in ["btn-pivots", "btn-hillshade", "btn-slope", "btn-contours", "btn-soil"]:
        snippet_index = text.find(f'testid="{testid}"')
        assert snippet_index >= 0
        snippet = text[snippet_index : snippet_index + 350]
        assert "isOverlayBlocked" not in snippet
