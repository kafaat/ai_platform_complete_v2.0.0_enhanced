from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAPHUB = ROOT / "frontend/src/sections/MapHub.tsx"
SHELL = ROOT / "frontend/src/sections/maphub/MapHubShell.tsx"


def test_maphub_shell_component_exists_with_strangler_contract():
    text = SHELL.read_text(encoding="utf-8")
    assert "export function MapHubShell" in text
    assert "MAPHUB_SHELL_REGIONS" in text
    assert "field-list" in text
    assert "map-canvas" in text
    assert "layer-manager" in text
    assert "field-drawer" in text
    assert "MAPHUB_STRANGLER_PHASES" in text
    assert "ui5-shell" in text


def test_maphub_default_export_is_shell_wrapped_without_replacing_core_behavior():
    text = MAPHUB.read_text(encoding="utf-8")
    assert "import { MapHubShell } from './maphub/MapHubShell';" in text
    assert "function MapHubCore()" in text
    assert "export default function MapHub()" in text
    assert "<MapHubShell>" in text
    assert "<MapHubCore />" in text
    # Existing heavy behavior remains inside MapHub.tsx for this phase; this is a strangler-safe shell only.
    assert "useSelectedField({ routeFieldId })" in text
    assert "HubMap" in text
    assert "FieldDetailDrawer" in text
    assert "AddFieldWithMap" in text


def test_ui5_does_not_start_a_large_maphub_rewrite_yet():
    text = MAPHUB.read_text(encoding="utf-8")
    # This phase must not remove current rendering paths before visual/e2e parity exists.
    assert "FieldSplitMergeTool" in text
    assert "TerrainView3D" in text
    assert "HubMapGL" in text
    assert "LayerSwitcher" in text
    assert "SideBySide" in text
