import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_contract_and_brain_alignment():
    c = json.loads((ROOT / "shared/contracts/intelligence_governance.json").read_text())
    assert c["principles"]["observed_spectral_truth"] == "raster-service"
    assert c["principles"]["decision_authority"] == "decision-service"


def test_supervisor_reads_not_computes():
    for rel in [
        "services/supervisor-agent/remote_sensing_skill.py",
        "services/supervisor-agent/skills/remote_sensing_skill.py",
    ]:
        t = (ROOT / rel).read_text()
        assert '"compute_ndvi"' not in t
        assert "read_indicator_observation" in t
        assert "BRAIN_DIRECT_SATELLITE_FETCH_ENABLED" in t


def test_mcp_reads_raster_truth():
    t = (ROOT / "services/mcp_servers/sentinel_hub_server.py").read_text()
    assert "RASTER_SERVICE_URL" in t
    assert "authoritative raster observation unavailable" in t
