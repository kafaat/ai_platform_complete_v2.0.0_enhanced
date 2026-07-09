from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
ALLOWLIST_PATH = ROOT / "docs" / "architecture" / "raster_boundary_allowlist.json"
CONTRACT_PATH = ROOT / "docs" / "architecture" / "RASTER_FACADE_CLEANUP_CONTRACT.md"

DIRECT_SERVICE_WIRING_TOKENS = (
    "RASTER_SERVICE_URL",
    "DEFAULT_RASTER_SERVICE_URL",
    "http://sahool-raster-service",
    "sahool-raster-service:8001",
)

# Browser-facing alias paths are not service wiring. They are still constrained so
# /api/raster does not quietly spread through unrelated platform modules.
API_RASTER_ALIAS_TOKEN = "/api/raster"

EXPECTED_FACADE_EXPORTS = (
    "raster_get_json",
    "raster_post_json",
    "raster_get_raw",
    "raster_get_json_sync",
    "get_available_dates",
    "get_indicator_grid",
    "get_field_terrain",
    "get_provider_status_sync",
    "get_field_terrain_sync",
    "get_indices_sync",
    "process_field_cdse",
    "get_best_imagery_scene",
    "search_imagery_scenes",
    "process_field_from_stac",
    "process_indicator_batch",
    "get_job_result",
)


def _platform_py_files() -> list[Path]:
    return sorted(
        p
        for p in PLATFORM.rglob("*.py")
        if "/tests/" not in p.as_posix() and "__pycache__" not in p.as_posix()
    )


def _rel(path: Path) -> str:
    return path.relative_to(PLATFORM).as_posix()


def test_p2_5_final_sweep_contract_is_documented():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "P2.5" in text
    assert "Raster Direct Wiring Final Sweep" in text
    assert "direct raster-service URL/token/transport wiring" in text


def test_only_raster_facade_client_may_read_direct_raster_service_wiring():
    allow = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    allowed = set(allow.get("direct_service_wiring_allowed_files", {}))
    assert allowed == {"api/raster_service_client.py"}

    offenders: list[str] = []
    for path in _platform_py_files():
        rel = _rel(path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        hits = [token for token in DIRECT_SERVICE_WIRING_TOKENS if token in text]
        if hits and rel not in allowed:
            offenders.append(f"{rel}: {hits}")
    assert not offenders, (
        "Direct raster-service URL/token wiring must stay behind api/raster_service_client.py: "
        + repr(offenders[:20])
    )


def test_browser_api_raster_aliases_are_narrowly_allowlisted():
    allow = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    allowed = set(allow.get("browser_api_raster_alias_allowed_files", {}))
    expected = {
        "api/routers/compat_gateway.py",
        "api/routers/fields.py",
        "api/raster_service_client.py",
        # UI27-30: imagery timeline (+ its /api/raster browser thumbnail URLs) relocated
        # from fields.py into the Field Workspace imagery facade — same BFF pattern.
        "api/routers/field_workspace_imagery.py",
    }
    assert allowed == expected

    offenders: list[str] = []
    for path in _platform_py_files():
        rel = _rel(path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        if API_RASTER_ALIAS_TOKEN in text and rel not in allowed:
            offenders.append(rel)
    assert not offenders, (
        "/api/raster browser aliases must not spread beyond the documented BFF/compat files: "
        + repr(offenders[:20])
    )


def test_raster_facade_contains_all_p2_boundary_operations():
    text = (PLATFORM / "api" / "raster_service_client.py").read_text(encoding="utf-8")
    missing = [
        name
        for name in EXPECTED_FACADE_EXPORTS
        if f"def {name}" not in text and f"async def {name}" not in text
    ]
    assert not missing, f"Raster facade is missing P2 boundary operations: {missing}"


def test_allowlist_records_p2_5_final_sweep_status():
    allow = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    status = allow.get("final_sweep_status", "")
    assert "P2.5" in status
    assert "api/raster_service_client.py" in status
