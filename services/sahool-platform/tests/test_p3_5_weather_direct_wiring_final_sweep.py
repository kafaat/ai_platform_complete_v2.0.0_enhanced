"""P3.5 — weather direct-wiring final sweep guard.

Scans services/sahool-platform/api/**/*.py and asserts that every file referencing a direct
Open-Meteo wiring marker (import of api.connectors.openmeteo, or a call to
fetch_current/fetch_daily_forecast/fetch_historical/fetch_weather_tile_data) is either:
  - a legitimate home (the Open-Meteo provider adapter or the weather-service transport), or
  - a documented cross-domain residual in weather_direct_wiring_allowlist.json.

Any new offender fails the guard, preventing direct Open-Meteo wiring from re-spreading
through unrelated platform modules after the P3.4 facade extraction.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
API_DIR = PLATFORM / "api"
ALLOWLIST_PATH = ROOT / "docs" / "architecture" / "weather_direct_wiring_allowlist.json"
CONTRACT_PATH = ROOT / "docs" / "architecture" / "WEATHER_DIRECT_WIRING_FINAL_SWEEP_CONTRACT.md"

DIRECT_WIRING_MARKERS = (
    "connectors.openmeteo",
    "fetch_weather_tile_data",
    "fetch_current",
    "fetch_daily_forecast",
    "fetch_historical",
)


def _load_allowlist() -> dict:
    return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))


def _rel(path: Path) -> str:
    return path.relative_to(PLATFORM).as_posix()


def _api_py_files() -> list[Path]:
    return sorted(
        p
        for p in API_DIR.rglob("*.py")
        if "/tests/" not in p.as_posix() and "__pycache__" not in p.as_posix()
    )


def test_allowlist_markers_match_the_guard():
    allow = _load_allowlist()
    assert set(allow["direct_wiring_markers"]) == set(DIRECT_WIRING_MARKERS)


def test_every_direct_openmeteo_reference_is_a_home_or_documented_residual():
    allow = _load_allowlist()
    allowed = set(allow.get("legitimate_homes", {})) | set(
        allow.get("composite_residuals_pending_p4", {})
    )

    offenders: list[str] = []
    for path in _api_py_files():
        rel = _rel(path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        hits = [m for m in DIRECT_WIRING_MARKERS if m in text]
        if hits and rel not in allowed:
            offenders.append(f"{rel}: {hits}")
    assert not offenders, (
        "New direct Open-Meteo wiring must go through weather-service "
        "(api/weather_service_client.py) or the provider adapter "
        "(api/connectors/openmeteo.py), or be documented as a residual in "
        "weather_direct_wiring_allowlist.json: " + repr(offenders[:20])
    )


def test_allowlist_residuals_and_homes_are_not_stale():
    """Every allowlisted file must exist and actually still reference a marker (no dead
    entries that would hide a future regression)."""
    allow = _load_allowlist()
    listed = set(allow.get("legitimate_homes", {})) | set(
        allow.get("composite_residuals_pending_p4", {})
    )
    stale: list[str] = []
    for rel in listed:
        path = PLATFORM / rel
        if not path.exists():
            stale.append(f"{rel}: missing file")
            continue
        # weather_service_client.py is a sanctioned home that does not import the openmeteo
        # markers (it speaks to weather-service), so it is exempt from the "must reference a
        # marker" check.
        if rel == "api/weather_service_client.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not any(m in text for m in DIRECT_WIRING_MARKERS):
            stale.append(f"{rel}: no longer references any direct marker (remove from allowlist)")
    assert not stale, repr(stale)


def test_legitimate_homes_are_exactly_the_two_sanctioned_files():
    allow = _load_allowlist()
    assert set(allow.get("legitimate_homes", {})) == {
        "api/connectors/openmeteo.py",
        "api/weather_service_client.py",
    }


def test_final_sweep_contract_is_documented():
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "P3.5" in text
    assert "Weather Direct Wiring Final Sweep" in text
    assert "api/weather_service_client.py" in text
    assert "api/connectors/openmeteo.py" in text
    status = _load_allowlist().get("final_sweep_status", "")
    assert "P3.5" in status
