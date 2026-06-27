import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RASTER_MAIN = ROOT / "services" / "raster-service" / "main.py"
COMPOSE = ROOT / "docker-compose.v9.yml"


def test_tile_observability_metrics_and_endpoint_are_present():
    src = RASTER_MAIN.read_text()
    assert "_TILE_OBS" in src
    assert "sahool_raster_tilejson_requests_total" in src
    assert "sahool_raster_tile_transparent_total" in src
    assert '@app.get("/v1/tiles/observability")' in src


def test_tilejson_returns_clear_no_scene_reason_and_action():
    src = RASTER_MAIN.read_text()
    # متين ضدّ لفّ ruff للتعبير الشرطيّ على أسطر متعدّدة: نُسطّح المسافات قبل الفحص
    # كي يحرس البنية (reason/user_message/recommended_action الشرطيّة) لا التنسيق.
    flat = re.sub(r"\s+", " ", src)
    assert '"reason": None if has_data else "no_field_cog_or_scene_available"' in flat
    assert '"user_message": None if has_data else' in flat
    assert '"recommended_action": None if has_data else' in flat
    assert "imagery/backfill" in src


def test_tile_endpoint_counts_cache_and_transparent_fallback():
    src = RASTER_MAIN.read_text()
    assert '_obs_inc("tile_requests_total", index)' in src
    assert '_obs_inc("tile_cache_hits_total", index)' in src
    assert '_obs_inc("tile_cache_misses_total", index)' in src
    assert '_obs_inc("tile_transparent_total", index)' in src
    assert '_obs_inc("tile_render_errors_total", index)' in src


def test_soil_service_is_enabled_in_compose_for_readyz():
    src = COMPOSE.read_text()
    assert "sahool-soil-service:" in src
    assert "services/soil-service/Dockerfile" in src
    assert "SAHOOL_AGENT_TOKEN" in src
    assert "http://localhost:8000/readyz" in src
