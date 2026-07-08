from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "sahool-platform"
FIELD_AI_CONTEXT = PLATFORM / "api" / "routers" / "field_ai_context.py"
RASTER_CLIENT = PLATFORM / "api" / "raster_service_client.py"

REQUIRED_FACADE_IMPORTS = {
    "get_available_dates",
    "get_indicator_grid",
}

FORBIDDEN_DIRECT_RASTER_TOKENS = {
    "httpx.AsyncClient",
    "RASTER_SERVICE_URL",
    "sahool-raster-service",
    "raster_url",
    "SAHOOL_AGENT_TOKEN",
    "X-Agent-Token",
}

REQUIRED_CLIENT_HELPERS = {
    "get_available_dates",
    "get_indicator_grid",
}


def _imported_from_raster_facade(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "api.raster_service_client":
            imported.update(alias.name for alias in node.names)
    return imported


def test_field_ai_context_uses_raster_facade_for_imagery_pack():
    imported = _imported_from_raster_facade(FIELD_AI_CONTEXT)
    missing = REQUIRED_FACADE_IMPORTS - imported
    assert not missing, f"field_ai_context imagery pack must use raster facade imports: {missing}"


def test_field_ai_context_has_no_direct_raster_http_or_secret_wiring():
    text = FIELD_AI_CONTEXT.read_text()
    offenders = sorted(token for token in FORBIDDEN_DIRECT_RASTER_TOKENS if token in text)
    assert not offenders, (
        "field_ai_context must not wire raster-service URL/token/httpx directly; "
        f"use api.raster_service_client instead: {offenders}"
    )


def test_raster_facade_exposes_field_ai_context_helpers():
    text = RASTER_CLIENT.read_text()
    missing = [
        f"async def {name}" for name in REQUIRED_CLIENT_HELPERS if f"async def {name}" not in text
    ]
    assert not missing, f"raster facade is missing field AI context helpers: {missing}"
