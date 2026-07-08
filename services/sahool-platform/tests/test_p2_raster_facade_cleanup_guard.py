from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
CONTRACT_PATH = ROOT / "docs" / "architecture" / "RASTER_FACADE_CLEANUP_CONTRACT.md"
ALLOWLIST_PATH = ROOT / "docs" / "architecture" / "raster_boundary_allowlist.json"

CLEANED_FILES = {
    "api/routers/fields.py",
    "api/routers/etc_dual.py",
    "api/imagery_automation.py",
}

REQUIRED_CLIENT_FUNCS = {
    "api/routers/fields.py": {
        "get_available_dates",
        "start_imagery_backfill",
        "get_imagery_backfill_status",
        "get_field_terrain",
    },
    "api/routers/etc_dual.py": {"get_indicator_grid"},
    "api/imagery_automation.py": {
        "get_best_imagery_scene",
        "get_job_result",
        "process_field_cdse",
        "process_field_from_stac",
        "process_indicator_batch",
        "raster_service_url",
        "search_imagery_scenes",
    },
}


def _imports_from_raster_client(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "api.raster_service_client":
            for alias in node.names:
                names.add(alias.name)
    return names


def test_p2_contract_and_client_are_present():
    assert CONTRACT_PATH.exists(), "P2 raster cleanup contract must be documented"
    client = PLATFORM / "api" / "raster_service_client.py"
    assert client.exists(), "sahool-platform must have a single raster facade client"
    text = client.read_text(encoding="utf-8")
    for token in [
        "raster_get_json",
        "raster_post_json",
        "get_available_dates",
        "start_imagery_backfill",
        "get_imagery_backfill_status",
        "get_indicator_grid",
        "get_field_terrain",
        "get_job_result",
        "process_indicator_batch",
        "process_field_from_stac",
        "search_imagery_scenes",
        "get_best_imagery_scene",
        "process_field_cdse",
        "X-Agent-Token",
        "X-Tenant-Id",
    ]:
        assert token in text


def test_cleaned_routes_import_the_raster_facade_client():
    for rel, expected in REQUIRED_CLIENT_FUNCS.items():
        imported = _imports_from_raster_client(PLATFORM / rel)
        missing = expected - imported
        assert not missing, (
            f"{rel} must use api.raster_service_client for P2-cleaned raster calls: {missing}"
        )


def test_cleaned_routes_do_not_open_code_raster_httpx_calls():
    offenders = []
    for rel in CLEANED_FILES:
        text = (PLATFORM / rel).read_text(encoding="utf-8", errors="ignore")
        if "RASTER_SERVICE_URL" in text or "sahool-raster-service" in text:
            offenders.append(f"{rel} still reads raster URL directly")
        if "httpx.AsyncClient" in text and "open-meteo" not in text.lower():
            offenders.append(f"{rel} still open-codes async HTTP client calls")
    assert not offenders, repr(offenders)


def test_raster_facade_client_is_allowlisted_as_boundary_file():
    allow = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    assert "api/raster_service_client.py" in allow["allowed_platform_files"]
    assert "facade_client" in allow["allowed_platform_files"]["api/raster_service_client.py"]
