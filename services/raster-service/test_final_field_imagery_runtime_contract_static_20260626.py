"""Final static regression checks for field/imagery/map runtime wiring."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_field_indicator_map_uses_tilejson_cache_version_for_tile_url():
    src = read("frontend/src/components/FieldIndicatorMap.tsx")
    # باني رابط بلاطة المؤشّر استُخرِج إلى imageryApi.ts (يُعاد تصديره من api.ts عبر
    # export *)؛ نفحص كليهما كي يحرس العقد لا موضع التعريف.
    api = read("frontend/src/services/api.ts") + read("frontend/src/services/imageryApi.ts")
    assert "cache_version" in src
    assert "setTileCacheVersion(r.data?.cache_version" in src
    assert (
        "fieldIndicatorTileUrl(fieldId, normalizedIndex, date, tenantId, tileCacheVersion)" in src
    )
    assert "cacheVersion?: string | number | null" in api
    assert "params.set('v', String(cacheVersion))" in api


def test_scouting_map_propagates_tenant_to_raster_tile_images():
    src = read("frontend/src/components/fieldhealth/ScoutingMap.tsx")
    assert "getTenantId()" in src
    assert "fieldIndicatorTileUrl" in src
    assert "indicatorTileUrl(fieldId, index, date, tenantId)" in src
    assert "return `${RASTER}/v1/fields" not in src


def test_field_map_center_uses_real_imagery_dates_not_forced_latest():
    src = read("frontend/src/sections/FieldMapCenter.tsx")
    assert "fetchFieldImageryAvailableDates" in src
    assert "selectedDate" in src
    assert "date={selectedDate}" in src
    assert 'date="latest"' not in src


def test_forensic_red_flags_absent_from_runtime_sources():
    runtime_files = [
        "frontend/src/components/maphub/HubMapGL.tsx",
        "frontend/src/components/maphub/HubMap.tsx",
        "frontend/src/components/FieldIndicatorMap.tsx",
        "frontend/src/components/fieldhealth/ScoutingMap.tsx",
        "services/raster-service/main.py",
    ]
    text = "\n".join(read(p) for p in runtime_files)
    assert "setTiles(" not in text
    assert "nodata=None" not in text
    assert "geometry.bounds" not in text
    assert 'method="first"' not in text
    assert "method='first'" not in text


def test_phase_9_10_hardening_migration_is_manifested():
    manifest = read("migrations/MANIFEST.txt")
    assert "v107_phase9_10_event_drift_hardening.sql" in manifest
