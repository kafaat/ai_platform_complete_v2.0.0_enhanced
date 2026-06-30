import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_service_registry_exists_and_mentions_core_services():
    registry = (ROOT / "SERVICE_REGISTRY.md").read_text(encoding="utf-8")
    assert "sahool-platform" in registry
    assert "raster-service" in registry
    assert "weather" in registry.lower()
    assert "ai_agronomist" in registry
    assert "Field Intelligence Backbone" in registry


def test_raw_imagery_default_is_protected_in_adr():
    adr = (ROOT / "docs/backend/ADR_V50_BACKEND_OWNERSHIP_AND_RAW_IMAGERY_DEFAULT.md").read_text(
        encoding="utf-8"
    )
    assert "raw field satellite imagery" in adr
    assert "truecolor" in adr
    assert "default MapHub" in adr
    assert "Weather and vegetation indices are overlays" in adr


def test_generated_inventory_has_service_counts_and_risks():
    inventory = json.loads(
        (ROOT / "docs/backend/service_inventory.generated.json").read_text(encoding="utf-8")
    )
    names = {item["service"] for item in inventory}
    assert len(inventory) >= 20
    assert "sahool-platform" in names
    assert "raster-service" in names
    assert "weather-service" in names
    platform = next(item for item in inventory if item["service"] == "sahool-platform")
    assert platform["risk"] == "critical-core-concentration"
    assert platform["route_count"] > 100


def test_backend_roadmap_contains_job_lifecycle_and_ai_evidence():
    roadmap = (ROOT / "docs/backend/BACKEND_IMPROVEMENT_ROADMAP_V50.md").read_text(encoding="utf-8")
    assert "Imagery Job Lifecycle" in roadmap
    assert "Evidence-grounded AI actions" in roadmap
    assert "24-month backfill" in roadmap
