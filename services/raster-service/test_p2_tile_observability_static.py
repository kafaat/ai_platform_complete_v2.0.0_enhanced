import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_RASTER_MAIN_PATH = ROOT / "services" / "raster-service" / "main.py"
COMPOSE = ROOT / "docker-compose.v9.yml"


class _CombinedSource:
    """توحيد main↔cert: المسارات فُكِّكت من main.py إلى routers/. ``read_text()`` يُرجِع
    المصدرَ المُجمَّع (main.py + routers/*.py) كي تبقى تأكيدات الكود صحيحة بعد التفكيك."""

    def read_text(self, *a, **k) -> str:
        root = _RASTER_MAIN_PATH.parent
        rdir = root / "routers"
        parts = [_RASTER_MAIN_PATH.read_text(encoding="utf-8")]
        for extra in ("raster_main_compat_exports.py", "tile_observability.py"):
            parts.append((root / extra).read_text(encoding="utf-8"))
        parts += [
            Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(rdir / "*.py")))
        ]
        return "\n".join(parts)


RASTER_MAIN = _CombinedSource()


def test_tile_observability_metrics_and_endpoint_are_present():
    src = RASTER_MAIN.read_text(encoding="utf-8")
    assert "_TILE_OBS" in src
    assert "sahool_raster_tilejson_requests_total" in src
    assert "sahool_raster_tile_transparent_total" in src
    assert '.get("/v1/tiles/observability")' in src  # @app→@router بعد التفكيك


def test_tilejson_returns_clear_no_scene_reason_and_action():
    # توحيد main↔cert: نُطبّع المسافات لأنّ ruff قد يلفّ التعبير الثلاثيّ عبر أسطر بعد
    # التفكيك — السلوك محفوظ، فنطابق المضمون لا التنسيق.
    src = " ".join(RASTER_MAIN.read_text(encoding="utf-8").split())
    assert '"reason": None if has_data else "no_field_cog_or_scene_available"' in src
    assert '"user_message": None if has_data else' in src
    assert '"recommended_action": None if has_data else' in src
    assert "imagery/backfill" in src


def test_tile_endpoint_counts_cache_and_transparent_fallback():
    src = RASTER_MAIN.read_text(encoding="utf-8")
    assert '_obs_inc("tile_requests_total", index)' in src
    assert '_obs_inc("tile_cache_hits_total", index)' in src
    assert '_obs_inc("tile_cache_misses_total", index)' in src
    assert '_obs_inc("tile_transparent_total", index)' in src
    assert '_obs_inc("tile_render_errors_total", index)' in src


def test_soil_service_is_enabled_in_compose_for_readyz():
    src = COMPOSE.read_text(encoding="utf-8")
    assert "sahool-soil-service:" in src
    assert "services/soil-service/Dockerfile" in src
    assert "SAHOOL_AGENT_TOKEN" in src
    assert "http://localhost:8000/readyz" in src
