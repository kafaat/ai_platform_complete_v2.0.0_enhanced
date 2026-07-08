from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
ADAPTERS = PLATFORM / "core" / "field_intelligence_adapters.py"
RASTER_CLIENT = PLATFORM / "api" / "raster_service_client.py"
CONTRACT = ROOT / "docs" / "architecture" / "RASTER_FACADE_CLEANUP_CONTRACT.md"

REQUIRED_IMPORTS = {
    "get_provider_status_sync",
    "get_field_terrain_sync",
    "get_indices_sync",
}

FORBIDDEN_DIRECT_RASTER_TOKENS = {
    "RASTER_SERVICE_URL",
    "sahool-raster-service",
    "RASTER_URL",
    'f"{RASTER_URL}',
    "http://sahool-raster-service",
}

REQUIRED_CLIENT_HELPERS = REQUIRED_IMPORTS | {"raster_get_json_sync"}


def _imports_from_raster_facade(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "api.raster_service_client":
            imported.update(alias.name for alias in node.names)
    return imported


def test_field_intelligence_adapters_use_sync_raster_facade():
    imported = _imports_from_raster_facade(ADAPTERS)
    missing = REQUIRED_IMPORTS - imported
    assert not missing, (
        f"field intelligence adapters must use raster facade sync helpers: {missing}"
    )


def test_field_intelligence_adapters_do_not_wire_raster_transport_directly():
    text = ADAPTERS.read_text(encoding="utf-8", errors="ignore")
    offenders = sorted(token for token in FORBIDDEN_DIRECT_RASTER_TOKENS if token in text)
    assert not offenders, (
        "field_intelligence_adapters must not build raster-service URL/token wiring directly; "
        f"use api.raster_service_client instead: {offenders}"
    )


def test_raster_facade_exposes_sync_fail_soft_helpers():
    text = RASTER_CLIENT.read_text(encoding="utf-8", errors="ignore")
    missing = [f"def {name}" for name in REQUIRED_CLIENT_HELPERS if f"def {name}" not in text]
    assert not missing, f"raster facade is missing sync field-intelligence helpers: {missing}"


def test_p2_3_contract_is_documented():
    text = CONTRACT.read_text(encoding="utf-8", errors="ignore")
    assert "P2.3" in text
    assert "field_intelligence_adapters.py" in text
    for helper in REQUIRED_IMPORTS:
        assert helper in text
