"""S5 provider ownership/end-state witnesses.

Provider implementations that have a canonical runtime path must not remain as
dead duplicate clients under sahool-platform.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]


def _production_imports(pattern: str) -> list[str]:
    rx = re.compile(pattern)
    out = []
    for p in sorted((ROOT / "services").rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if "/tests/" in rel or p.name.startswith("test_"):
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if rx.search(txt):
            out.append(rel)
    return out


def test_cdse_provider_is_owned_by_raster_service():
    assert not (ROOT / "services/sahool-platform/core/connectors/copernicus.py").exists()
    owner = ROOT / "services/raster-service/cdse_client.py"
    assert owner.is_file()
    s = owner.read_text(encoding="utf-8")
    for token in ("CDSE_CLIENT_ID", "CDSE_CLIENT_SECRET", "SH_TOKEN_URL", "SH_BASE_URL",
                  "def is_configured", "def get_client", "class CdseClient"):
        assert token in s
    assert _production_imports(r"core\.connectors\.copernicus|CopernicusConnector") == []


def test_openmeteo_provider_uses_canonical_api_connector_only():
    legacy = ROOT / "services/sahool-platform/core/connectors/weather_openmeteo.py"
    owner = ROOT / "services/sahool-platform/api/connectors/openmeteo.py"
    assert not legacy.exists()
    assert owner.is_file()
    src = owner.read_text(encoding="utf-8")
    for token in ("FORECAST_URL", "HISTORICAL_URL", "CircuitBreaker", "httpx.AsyncClient"):
        assert token in src
    assert _production_imports(r"core\.connectors\.weather_openmeteo|OpenMeteoConnector") == []
