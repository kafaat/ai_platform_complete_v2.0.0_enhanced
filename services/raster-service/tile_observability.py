"""Tile/tilejson observability counters for raster-service.

Kept deliberately in-process and low-cardinality.  main.py re-exports the
state during staged decomposition so routers/tests that still import main._obs_inc
continue to work.
"""

from __future__ import annotations

TILE_OBS: dict[str, int] = {
    "tilejson_requests_total": 0,
    "tilejson_available_total": 0,
    "tilejson_unavailable_total": 0,
    "tile_requests_total": 0,
    "tile_cache_hits_total": 0,
    "tile_cache_misses_total": 0,
    "tile_transparent_total": 0,
    "tile_render_errors_total": 0,
}
TILE_OBS_BY_INDEX: dict[str, dict[str, int]] = {}


def obs_inc(name: str, index: str | None = None, amount: int = 1) -> None:
    """Increment a tile/tilejson counter.

    The function intentionally accepts unknown names to keep the diagnostic
    endpoint forward-compatible with new counters added by routers.
    """
    TILE_OBS[name] = int(TILE_OBS.get(name, 0)) + amount
    if index:
        bucket = TILE_OBS_BY_INDEX.setdefault(index, {})
        bucket[name] = int(bucket.get(name, 0)) + amount
