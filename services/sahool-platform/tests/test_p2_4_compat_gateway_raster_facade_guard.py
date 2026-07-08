from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
TARGET = PLATFORM / "api" / "routers" / "compat_gateway.py"
CLIENT = PLATFORM / "api" / "raster_service_client.py"
CONTRACT = ROOT / "docs" / "architecture" / "RASTER_FACADE_CLEANUP_CONTRACT.md"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _raster_api_function_node() -> ast.AsyncFunctionDef:
    tree = ast.parse(_source(TARGET))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "raster_api_passthrough":
            return node
    raise AssertionError("compat_gateway.raster_api_passthrough must exist")


def test_compat_gateway_imports_raster_raw_facade():
    tree = ast.parse(_source(TARGET))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "api.raster_service_client":
            imported.update(alias.name for alias in node.names)
    assert "raster_get_raw" in imported


def test_raster_passthrough_no_longer_owns_raster_transport_wiring():
    node = _raster_api_function_node()
    func_text = ast.get_source_segment(_source(TARGET), node) or ""
    forbidden = [
        "RASTER_SERVICE_URL",
        "sahool-raster-service",
        "httpx.AsyncClient",
        "client.get(",
        "X-Agent-Token",
    ]
    hits = [token for token in forbidden if token in func_text]
    assert not hits, f"raster legacy passthrough must delegate transport to raster_get_raw: {hits}"
    assert "raster_get_raw(" in func_text


def test_raster_client_exposes_raw_get_for_legacy_tiles():
    text = _source(CLIENT)
    for token in [
        "async def raster_get_raw",
        "raster_service_url()",
        "raster_service_headers",
        "Authorization",
        "cache-control",
        "last-modified",
        "etag",
    ]:
        assert token in text


def test_contract_documents_p2_4_compat_gateway_cleanup():
    text = _source(CONTRACT)
    assert "P2.4" in text
    assert "compat_gateway.py" in text
    assert "raster_get_raw" in text
