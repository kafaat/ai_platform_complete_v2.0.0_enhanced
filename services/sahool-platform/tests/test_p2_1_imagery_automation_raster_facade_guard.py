from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
IMAGERY_AUTOMATION = PLATFORM / "api" / "imagery_automation.py"
RASTER_CLIENT = PLATFORM / "api" / "raster_service_client.py"
REPORT = ROOT / "P2_1_IMAGERY_AUTOMATION_RASTER_FACADE_REPORT.md"

REQUIRED_FACADE_IMPORTS = {
    "get_best_imagery_scene",
    "get_job_result",
    "process_field_cdse",
    "process_field_from_stac",
    "process_indicator_batch",
    "raster_service_url",
    "search_imagery_scenes",
}


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8", errors="ignore"))


def _imported_from_raster_client() -> set[str]:
    names: set[str] = set()
    for node in ast.walk(_tree(IMAGERY_AUTOMATION)):
        if isinstance(node, ast.ImportFrom) and node.module == "api.raster_service_client":
            names.update(alias.name for alias in node.names)
    return names


def test_imagery_automation_uses_raster_facade_imports_only():
    missing = REQUIRED_FACADE_IMPORTS - _imported_from_raster_client()
    assert not missing, (
        f"imagery_automation must call raster-service through facade client: {missing}"
    )


def test_imagery_automation_has_no_direct_http_client_or_raster_url_reads():
    text = IMAGERY_AUTOMATION.read_text(encoding="utf-8", errors="ignore")
    forbidden = [
        "import httpx",
        "httpx.AsyncClient",
        "RASTER_SERVICE_URL",
        "sahool-raster-service",
        "_RASTER_HEADERS",
        "SAHOOL_AGENT_TOKEN",
    ]
    offenders = [token for token in forbidden if token in text]
    assert not offenders, f"imagery_automation must not open-code raster transport: {offenders}"


def test_raster_facade_exposes_automation_primitives():
    text = RASTER_CLIENT.read_text(encoding="utf-8")
    for token in REQUIRED_FACADE_IMPORTS - {"raster_service_url"}:
        assert f"async def {token}" in text, f"raster facade missing {token}"
    for endpoint in [
        "/v1/fields/{field_id}/process-cdse",
        "/imagery/best",
        "/imagery/search",
        "/v1/fields/{field_id}/process-from-stac",
        "/process/batch",
        "/jobs/{job_id}/result",
    ]:
        assert endpoint in text, f"raster facade must own endpoint path {endpoint}"


def test_p2_1_report_exists():
    assert REPORT.exists(), "P2.1 imagery automation raster facade report must be present"
