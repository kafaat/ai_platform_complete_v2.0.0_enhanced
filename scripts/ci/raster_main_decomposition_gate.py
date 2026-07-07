#!/usr/bin/env python3
"""Raster-service main.py decomposition contract gate.

This guard keeps the ongoing main.py breakup honest without forcing a risky big-bang
rewrite. It verifies that the policy/helper/runtime chunks extracted from main.py stay
outside the application module and that production raster modules do not depend on
``main.py`` as a runtime dependency.
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
        "stac_health",
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
    "raster_pixel_processing.py": [
        "process_precomputed_pixels",
        "process_precomputed_truecolor",
        "process_pixels",
    ],
    "raster_cdse_processing.py": [
        "run_cdse_processing",
    ],
    "raster_api_models.py": [
        "IndicatorKind",
        "SourceFormat",
        "JobStatus",
        "BandMapping",
        "ProcessRequest",
        "BatchProcessRequest",
        "HistoricalBackfillRequest",
        "ProcessCdseRequest",
        "TimeSeriesAnalyzeRequest",
        "PrescriptionRequest",
        "SalinityFitRequest",
    ],
    "raster_security_context.py": [
        "REQ_TENANT",
        "tenant_from_header",
        "tenant_from_request",
        "field_owner",
        "require_field_tenant",
        "require_layer_tenant",
        "require_layer_tenant_authorized",
        "public_cog_url",
        "safe_raster_source",
        "require_service_token",
    ],
    "raster_quality.py": [
        "INDICATOR_FORMULAS",
        "quality_from_cloud_pct",
        "pixel_quality",
        "compute_cloud_pct",
    ],
    "tile_observability.py": [
        "TILE_OBS",
        "TILE_OBS_BY_INDEX",
        "obs_inc",
    ],
    "layer_cache_events.py": [
        "DEFAULT_LAYER_EVICT_CHANNEL",
        "layer_evict_enabled",
        "evict_field_layers",
        "layer_evict_subscriber",
    ],
    "raster_app_lifecycle.py": [
        "make_lifespan",
    ],
    "raster_settings.py": [
        "EARTH_SEARCH_URL",
        "HISTORICAL_SEARCH_PROVIDER",
        "CORS_ORIGINS",
        "HTTP_TIMEOUT",
        "UPLOAD_DIR",
        "SSRF_BLOCKED_HOSTS",
        "AGENT_TOKEN",
        "TRANSPARENT_PNG",
        "RASTER_NODATA",
        "stac_fallback_chain",
    ],
    "raster_backfill_scene_processing.py": [
        "process_backfill_scene_cdse",
    ],
    "raster_runtime_state.py": [
        "make_job_store",
        "JOBS",
        "LAYERS",
        "FIELD_LAYERS",
    ],
    "raster_processing_runtime.py": [
        "make_processing_context",
        "run_processing",
        "run_batch_processing",
        "process_precomputed_pixels",
        "process_precomputed_truecolor",
        "process_pixels",
    ],
    "raster_cdse_tile_runtime.py": [
        "parse_poly",
        "normalize_cdse_request",
        "ensure_field_cog",
        "tilejson_availability",
    ],
    "raster_field_runtime.py": [
        "_require_service_token",
        "_require_field_tenant",
        "_safe_raster_source",
        "_stac_search",
        "_stac_search_landsat_unique",
        "_run_processing",
        "_run_cdse_processing",
        "_process_backfill_scene_cdse",
        "_upload_dir",
    ],
}

MAX_MAIN_LINES = 530

DIRECT_ROUTER_IMPORTS = {
    "routers/jobs.py",
    "routers/imagery.py",
    "routers/imagery_search.py",
    "routers/processing.py",
    "routers/observability.py",
    "routers/analysis.py",
    "routers/soil_tiles.py",
    "routers/terrain_tiles.py",
    "routers/tiles.py",
    "routers/cdse_tiles.py",
    "routers/timeseries_routes.py",
    "routers/storage.py",
    "routers/fields.py",
    "routers/stac.py",
}
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
    "IndicatorKind",
    "SourceFormat",
    "JobStatus",
    "BandMapping",
    "ProcessRequest",
    "BatchProcessRequest",
    "SearchRequest",
    "HistoricalBackfillPreset",
    "HistoricalBackfillRequest",
    "AutoBackfillPolicy",
    "SceneCandidate",
    "SceneRankRequest",
    "MosaicPlanRequest",
    "GeoParquetExportRequest",
    "TimeSeriesAnalyzeRequest",
    "ManagementZonesRequest",
    "ChangeDetectRequest",
    "FvcComputeRequest",
    "SarRviRequest",
    "TerrainRequest",
    "ProcessFromStacRequest",
    "ProcessCdseRequest",
    "PrescriptionRequest",
    "FieldChangeRequest",
    "SalinityClassifyRequest",
    "SalinityFitRequest",
    "_quality_from_cloud_pct",
    "_pixel_quality",
    "lifespan",
}
REQUIRED_MAIN_ALIASES = {
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
    "import raster_processing_runtime",
    "return raster_processing_runtime.run_processing(job_id, req, upload_dir=UPLOAD_DIR)",
    "return raster_processing_runtime.run_batch_processing(job_id, req, upload_dir=UPLOAD_DIR)",
    "return raster_processing_runtime.process_precomputed_pixels(req, layer_id, upload_dir=UPLOAD_DIR)",
    "return raster_processing_runtime.process_precomputed_truecolor(req, upload_dir=UPLOAD_DIR)",
    "return raster_processing_runtime.process_pixels(req, layer_id, upload_dir=UPLOAD_DIR)",
    "import raster_cdse_processing",
    "ctx = raster_processing_runtime.make_processing_context(upload_dir=UPLOAD_DIR)",
    "return raster_cdse_processing.run_cdse_processing(ctx, job_id, field_id, req)",
    "from raster_api_models import",
    "BACKFILL_PRESET_MONTHS as _BACKFILL_PRESET_MONTHS",
    "ProcessCdseRequest, ProcessFromStacRequest",
    "FieldChangeRequest, PrescriptionRequest",
    "SalinityClassifyRequest, SalinityFitRequest",
    "import raster_security_context",
    "_REQ_TENANT = raster_security_context.REQ_TENANT",
    "return raster_security_context.tenant_from_header(value)",
    "return raster_security_context.safe_raster_source(url, UPLOAD_DIR, _SSRF_BLOCKED_HOSTS)",
    "return raster_security_context.require_service_token(x_agent_token, AGENT_TOKEN)",
    "import raster_quality",
    "_INDICATOR_FORMULAS = raster_quality.INDICATOR_FORMULAS",
    "_quality_from_cloud_pct = raster_quality.quality_from_cloud_pct",
    "_pixel_quality = raster_quality.pixel_quality",
    "import tile_observability",
    "_TILE_OBS = tile_observability.TILE_OBS",
    "_TILE_OBS_BY_INDEX = tile_observability.TILE_OBS_BY_INDEX",
    "_obs_inc = tile_observability.obs_inc",
    "import layer_cache_events",
    "_LAYER_EVICT_CHANNEL = layer_cache_events.DEFAULT_LAYER_EVICT_CHANNEL",
    "return layer_cache_events.layer_evict_enabled()",
    "return layer_cache_events.evict_field_layers(",
    "return await layer_cache_events.layer_evict_subscriber(",
    "import raster_app_lifecycle",
    "lifespan = raster_app_lifecycle.make_lifespan(",
    "import raster_settings",
    "EARTH_SEARCH_URL = raster_settings.EARTH_SEARCH_URL",
    "UPLOAD_DIR = raster_settings.UPLOAD_DIR",
    "_SSRF_BLOCKED_HOSTS = raster_settings.SSRF_BLOCKED_HOSTS",
    "AGENT_TOKEN = raster_settings.AGENT_TOKEN",
    "_fallback_chain = raster_settings.stac_fallback_chain()",
    "import raster_backfill_scene_processing",
    "return raster_backfill_scene_processing.process_backfill_scene_cdse(",
    "import raster_runtime_state",
    "_jobs = raster_runtime_state.JOBS",
    "_layers = raster_runtime_state.LAYERS",
    "_field_layers = raster_runtime_state.FIELD_LAYERS",
    "_TRANSPARENT_PNG = raster_settings.TRANSPARENT_PNG",
    "RASTER_NODATA = raster_settings.RASTER_NODATA",
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
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        # Constants exported from extracted modules are assignments, not defs.
        mod_defs.update(
            target.id
            for node in mod_tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        )
        mod_defs.update(
            node.target.id
            for node in mod_tree.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        )
        missing = [name for name in exports if name not in mod_defs]
        if missing:
            _fail(f"{module} missing expected exports: {missing}")

    for alias in REQUIRED_MAIN_ALIASES:
        if alias not in source:
            _fail(f"main.py compatibility alias missing: {alias}")

    dependency_scan_files = []
    for dep_path in sorted(SVC.rglob("*.py")):
        rel_parts = dep_path.relative_to(SVC).parts
        if dep_path.name == "main.py" or dep_path.name.startswith("test_"):
            continue
        if "__pycache__" in rel_parts:
            continue
        dependency_scan_files.append(dep_path)
    for dep_path in dependency_scan_files:
        rel = dep_path.relative_to(SVC).as_posix()
        dep_tree = ast.parse(dep_path.read_text(encoding="utf-8"))
        for node in ast.walk(dep_tree):
            if isinstance(node, ast.Import) and any(alias.name == "main" for alias in node.names):
                _fail(f"{rel} regressed to importing main instead of extracted modules directly")
            if isinstance(node, ast.ImportFrom) and node.module == "main":
                _fail(f"{rel} regressed to importing main instead of extracted modules directly")
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "main"
            ):
                _fail(f"{rel} regressed to using main.* instead of extracted modules directly")

    forbidden_sources = {
        "_jobs = JobStore(": "runtime job store must stay in raster_runtime_state.py",
        "_TRANSPARENT_PNG = bytes.fromhex(": "transparent PNG constant must stay in raster_settings.py",
        "RASTER_NODATA = -9999.0": "nodata constant must stay in raster_settings.py",
        "def compute_cloud_pct(": "cloud percentage helper must stay in raster_quality.py",
        "SCL_CLOUD_CLASSES =": "SCL cloud classes must stay in cdse_client.py",
        "_rank_scenes = scene_policy.rank_scenes": "scene ranking alias must not return to main.py",
        "_select_backfill_scenes_by_policy = scene_policy.select_backfill_scenes_by_policy": "backfill policy alias must not return to main.py",
        "_landsat_unique_payload = stac_search_helpers.landsat_unique_payload": "Landsat payload alias must not return to main.py",
        "def _tile_cache_key(": "tile cache key helper must stay in tile_cache_io.py",
        "_is_valid_field_id_text,": "field-id validation helper must stay in raster_asset_persistence.py",
        "sys.modules[__name__]": "processing wrappers must use explicit RasterRuntimeContext, not main.py as context",
        "import sys": "main.py must not import sys for context self-reference",
    }
    for needle, reason in forbidden_sources.items():
        if needle in source:
            _fail(reason)

    print(
        "raster-main-decomposition contract: OK "
        f"(main.py lines={line_count}, modules={len(REQUIRED_MODULES)})"
    )


if __name__ == "__main__":
    main()
