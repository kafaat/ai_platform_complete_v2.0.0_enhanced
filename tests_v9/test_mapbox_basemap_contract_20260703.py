from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_layer_registry_has_token_gated_mapbox_and_disabled_google() -> None:
    src = read("frontend/src/lib/layerRegistry.ts")
    assert "id: 'mapbox-satellite'" in src
    assert "id: 'maptiler-satellite'" in src
    assert "VITE_MAPTILER_KEY" in src
    assert "toMapLibreRasterUrl" in src
    assert "satellite-streets-v12" in src
    assert "requiresToken: true" in src
    assert "tokenEnv: 'VITE_MAPBOX_TOKEN'" in src
    assert "id: 'google-satellite-official'" in src
    assert "disabled: true" in src
    assert "لا تُستعمل روابط Google غير الرسمية" in src
    assert "resolveLayerSource" in src
    assert "availableBasemapLayers" in src


def test_add_field_map_uses_registry_basemap_selector_not_binary_toggle() -> None:
    src = read("frontend/src/components/AddFieldWithMap.tsx")
    assert "availableBasemapLayers" in src
    assert "resolveLayerSource" in src
    assert "ADD_FIELD_BASEMAPS.map" in src
    assert "<select" in src
    reg = read("frontend/src/lib/layerRegistry.ts")
    assert "VITE_MAPBOX_TOKEN" in reg
    assert "VITE_MAPTILER_KEY" in reg
    assert "tileType === 'street' ? 'satellite' : 'street'" not in src
    assert "selectedBasemapUrl" in src
    assert "maxZoom={selectedBasemapMaxZoom}" in src


def test_maphub_filters_available_basemaps_and_hub_renderers_resolve_tokens() -> None:
    section = read("frontend/src/sections/MapHub.tsx")
    assert "availableBasemapLayers(import.meta.env" in section
    assert "layersOfKind('basemap').map" not in section

    leaflet = read("frontend/src/components/maphub/HubMap.tsx")
    assert "resolveLayerSource(basemap, import.meta.env" in leaflet
    assert "basemapAttribution" in leaflet
    assert "basemapMaxZoom" in leaflet

    gl = read("frontend/src/components/maphub/HubMapGL.tsx")
    assert "resolveLayerSource(layer, import.meta.env" in gl
    assert "layer?.attribution" in gl
    assert "toMapLibreRasterUrl" in gl
