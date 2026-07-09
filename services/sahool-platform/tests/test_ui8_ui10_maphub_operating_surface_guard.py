from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"


def read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_ui8_map_canvas_boundary_exists_and_wraps_runtime_modes():
    src = read("sections/maphub/MapCanvasBoundary.tsx")
    assert "export function MapCanvasBoundary" in src
    assert "MapCanvasMode" in src
    for mode in ["leaflet", "maplibre", "compare", "terrain3d"]:
        assert mode in src
    assert 'data-testid="maphub-map-canvas-boundary"' in src
    assert 'data-sahool-region="map-canvas"' in src
    assert "data-map-canvas-mode" in src
    assert "data-field-id" in src
    assert "data-indicator-id" in src


def test_maphub_delegates_map_runtime_to_canvas_boundary_without_moving_hubmap_yet():
    src = read("sections/MapHub.tsx")
    assert "import { MapCanvasBoundary } from './maphub/MapCanvasBoundary';" in src
    assert "<MapCanvasBoundary" in src
    assert (
        "mode={mode === '3d' ? 'terrain3d' : compare ? 'compare' : GL_ENGINE ? 'maplibre' : 'leaflet'}"
        in src
    )
    assert "hasGeometry={Boolean(selected?.geometry)}" in src
    assert "</MapCanvasBoundary>" in src
    assert "<HubMap" in src and "<HubMapGL" in src


def test_ui9_field_context_strip_exposes_field_and_season_context():
    strip = read("sections/maphub/FieldContextStrip.tsx")
    assert "export function FieldContextStrip" in strip
    assert 'data-testid="maphub-field-context-strip"' in strip
    assert 'data-sahool-region="field-context"' in strip
    assert "fieldId" in strip
    assert "activeSeasonId" in strip
    assert "activeLayerId" in strip
    maphub = read("sections/MapHub.tsx")
    assert "import { FieldContextStrip } from './maphub/FieldContextStrip';" in maphub
    assert "<FieldContextStrip" in maphub
    assert "fieldId={fieldId}" in maphub
    assert "activeSeasonId={activeSeasonId}" in maphub


def test_ui10_priority_queue_panel_is_truthful_scaffold_not_fake_data():
    panel = read("sections/maphub/PriorityQueuePanel.tsx")
    assert "export function PriorityQueuePanel" in panel
    assert 'data-testid="maphub-priority-queue-panel"' in panel
    assert 'data-sahool-region="operational-priority-queue"' in panel
    assert "hasAlerts" in panel and "hasTasks" in panel and "hasWeatherWindow" in panel
    assert "لا تُبنى أولوية تشغيلية كاملة بدون موسم نشط" in panel
    assert "fake" not in panel.lower()
    maphub = read("sections/MapHub.tsx")
    assert "import { PriorityQueuePanel } from './maphub/PriorityQueuePanel';" in maphub
    assert "<PriorityQueuePanel" in maphub
    assert "hasAlerts={alertMarkers.length > 0}" in maphub
    assert "hasTasks={operationalMarkers.length > 0}" in maphub
    assert "hasWeatherWindow={Boolean(weatherMarker)}" in maphub
