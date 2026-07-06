#!/usr/bin/env python3
"""Raster-service main.py decomposition contract gate.

This guard keeps the ongoing main.py breakup honest without forcing a risky big-bang
rewrite. It verifies that the pure policy/helper chunks extracted from main.py stay
outside the application module and that main.py remains a compatibility façade for
routers/workers that still import ``main``.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SVC = ROOT / "services" / "raster-service"
MAIN = SVC / "main.py"

REQUIRED_MODULES = {
    "scene_policy.py": ["select_backfill_scenes_by_policy", "rank_scenes", "scene_quality_score"],
    "raster_date_geo.py": ["backfill_date_range", "bbox_from_geojson", "bbox_from_geom"],
    "tile_cache_io.py": ["tile_cache_key", "read_tile_cache", "write_tile_cache"],
    "cdse_singleflight.py": ["cdse_lock", "cdse_key_lock", "cdse_prune_key_locks_locked"],
    "stac_search.py": [
        "configure",
        "stac_search",
        "stac_search_cdse",
        "stac_search_element84",
        "stac_search_radar",
        "stac_search_landsat_unique",
        "stac_search_dem",
    ],
    "layer_lookup.py": [
        "normalize_index",
        "display_index",
        "find_field_layer",
        "grid_from_cog",
        "rehydrate_field_layer_from_db",
        "resolve_field_layer",
        "rvi_from_sar_cog",
        "real_field_grid",
    ],
    "raster_asset_persistence.py": [
        "_is_valid_uuid_text",
        "_is_valid_field_id_text",
        "persist_raster_asset",
    ],
    "raster_job_orchestration.py": [
        "run_processing",
        "run_batch_processing",
    ],
}

MAX_MAIN_LINES = 1950
FORBIDDEN_MAIN_DEFS = {
    # These names now live in modules and should not grow back into main.py.
    "_scene_quality_score",
    "_rank_scenes",
    "_select_backfill_scenes_by_policy",
    "_bbox_from_geojson",
    "_month_windows",
    "_cdse_key_lock",
    "_cdse_prune_key_locks_locked",
    "_stac_query",
    "_stac_search",
    "_stac_search_cdse",
    "_stac_search_element84",
    "_stac_search_radar",
    "_landsat_thermal_href",
    "_landsat_unique_payload",
    "_stac_search_landsat",
    "_stac_search_landsat_unique",
    "_stac_search_dem",
    "_is_valid_uuid_text",
    "_is_valid_field_id_text",
    "_persist_raster_asset",
}
REQUIRED_MAIN_ALIASES = {
    "_scene_quality_score = scene_policy.scene_quality_score",
    "_rank_scenes = scene_policy.rank_scenes",
    "_select_backfill_scenes_by_policy = scene_policy.select_backfill_scenes_by_policy",
    "_bbox_from_geojson = raster_date_geo.bbox_from_geojson",
    "_month_windows = raster_date_geo.month_windows",
    "_cdse_key_lock = cdse_singleflight.cdse_key_lock",
    "_stac_search = stac_search_helpers.stac_search",
    "_stac_search_cdse = stac_search_helpers.stac_search_cdse",
    "_stac_search_element84 = stac_search_helpers.stac_search_element84",
    "_stac_search_landsat_unique = stac_search_helpers.stac_search_landsat_unique",
    "import layer_lookup",
    "return layer_lookup.normalize_index(index)",
    "return await layer_lookup.resolve_field_layer(",
    "return await layer_lookup.real_field_grid(",
    "from raster_asset_persistence import",
    "persist_raster_asset as _persist_raster_asset",
    "import raster_job_orchestration",
    "return raster_job_orchestration.run_processing(sys.modules[__name__], job_id, req)",
    "return raster_job_orchestration.run_batch_processing(sys.modules[__name__], job_id, req)",
}


def _fail(msg: str) -> None:
    raise SystemExit(f"raster-main-decomposition contract failed: {msg}")


def main() -> None:
    if not MAIN.exists():
        _fail("services/raster-service/main.py is missing")
    source = MAIN.read_text(encoding="utf-8")
    line_count = len(source.splitlines())
    if line_count > MAX_MAIN_LINES:
        _fail(f"main.py grew to {line_count} lines; limit is {MAX_MAIN_LINES}")

    tree = ast.parse(source)
    defs = {
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    regressed = sorted(FORBIDDEN_MAIN_DEFS & defs)
    if regressed:
        _fail(f"extracted helper definitions returned to main.py: {regressed}")

    for module, exports in REQUIRED_MODULES.items():
        path = SVC / module
        if not path.exists():
            _fail(f"required extracted module missing: {module}")
        mod_tree = ast.parse(path.read_text(encoding="utf-8"))
        mod_defs = {
            node.name
            for node in mod_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        missing = [name for name in exports if name not in mod_defs]
        if missing:
            _fail(f"{module} missing expected exports: {missing}")

    for alias in REQUIRED_MAIN_ALIASES:
        if alias not in source:
            _fail(f"main.py compatibility alias missing: {alias}")

    print(
        "raster-main-decomposition contract: OK "
        f"(main.py lines={line_count}, modules={len(REQUIRED_MODULES)})"
    )


if __name__ == "__main__":
    main()
