import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "docs/architecture/SERVICE_REGISTRY_HARDENING_CONTRACT.json"
REGISTRY = ROOT / "docs/architecture/component_registry.json"


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


def test_a_noted_service_that_is_a_system_of_record_owns_a_declared_domain():
    """W1-11: indicators-service became a system of record (component_registry). A service this
    contract notes as a consumer/facade may be promoted only with an explicit ownership entry, so
    the two hand-kept sources cannot disagree about who owns a domain."""
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    owners = set(data["single_owner_domains"].values())
    components = json.loads(REGISTRY.read_text(encoding="utf-8"))["components"]
    for service in data["deprecated_or_duplicate_notes"]:
        entry = components.get(service)
        if entry and entry.get("authority_kind") == "system_of_record":
            assert service in owners, (
                f"{service} is a system_of_record in component_registry.json but owns no domain "
                "in SERVICE_REGISTRY_HARDENING_CONTRACT.json single_owner_domains"
            )
