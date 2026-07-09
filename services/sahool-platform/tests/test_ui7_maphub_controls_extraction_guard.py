from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"


def read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_operational_overlay_controls_component_exists_and_is_semantic():
    src = read("sections/maphub/OperationalOverlayControls.tsx")
    assert "export function OperationalOverlayControls" in src
    assert "OperationalOverlayControlsProps" in src
    assert 'data-testid="maphub-operational-overlay-controls"' in src
    assert 'data-sahool-region="operational-overlays"' in src
    for status in ["btn-weather", "btn-alerts", "btn-devices", "btn-equipment", "btn-tasks"]:
        assert status in src


def test_operational_overlay_controls_preserve_map_clutter_contract():
    src = read("sections/maphub/OperationalOverlayControls.tsx")
    assert "OperationalOverlayId" in src
    assert "isOverlayBlocked" in src
    assert "overlayBlockedTitle" in src
    for overlay in ["weather", "alerts", "devices", "equipment", "tasks"]:
        assert f"isOverlayBlocked('{overlay}')" in src
        assert f"overlayBlockedTitle('{overlay}')" in src


def test_maphub_delegates_operational_overlays_to_extracted_component():
    src = read("sections/MapHub.tsx")
    assert (
        "import { OperationalOverlayControls } from './maphub/OperationalOverlayControls';" in src
    )
    assert "<OperationalOverlayControls" in src
    assert "isVisible={!compare}" in src
    assert "setShowWeather={setShowWeather}" in src
    assert "hillshadeUnavailableMessage=" in src
    assert 'data-testid="maphub-operational-overlay-controls"' not in src


def test_tool_toggle_is_extracted_from_maphub():
    maphub = read("sections/MapHub.tsx")
    toggle = read("sections/maphub/MapHubToolToggle.tsx")
    assert "export function MapHubToolToggle" in toggle
    assert "function ToolToggle" not in maphub
    assert "<MapHubToolToggle" in maphub
    assert "import { MapHubToolToggle } from './maphub/MapHubToolToggle';" in maphub


def test_overlay_truthful_empty_states_remain_visible_after_extraction():
    src = read("sections/maphub/OperationalOverlayControls.tsx")
    maphub = read("sections/MapHub.tsx")
    assert "تنبيه غير قابل للعرض" in src
    assert "جهاز غير قابل للعرض" in src
    assert "معدّة غير قابلة للعرض" in src
    assert "مهمة غير قابلة للعرض" in src
    assert "hillshadeUnavailableMessage" in src and "التضاريس غير مُهيّأة" in maphub
    assert "slopeUnavailableMessage" in src and "طبقة الانحدار غير مُهيّأة" in maphub
