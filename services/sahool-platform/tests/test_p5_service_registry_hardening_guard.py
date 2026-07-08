import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "docs/architecture/SERVICE_REGISTRY_HARDENING_CONTRACT.json"


def test_single_owner_domains_are_declared_for_extracted_services():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    owners = data["single_owner_domains"]
    assert owners["raster"] == "raster-service"
    assert owners["weather"] == "weather-service"
    assert owners["decision_outcome_learning"] == "decision-service"
    assert len(set(owners.values())) >= 6


def test_duplicate_service_notes_are_explicit():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    notes = data["deprecated_or_duplicate_notes"]
    for service in (
        "indicators-service",
        "raster-tiler-service",
        "ai_agronomist",
        "supervisor-agent",
    ):
        assert service in notes
        assert notes[service]
