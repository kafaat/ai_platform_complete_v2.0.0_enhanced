import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/ci/capability_roadmap_linker.py"
spec = importlib.util.spec_from_file_location("capability_roadmap_linker", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def test_roadmap_links_are_valid_curated_and_fail_closed():
    data = mod.build()
    assert data["summary"]["roadmap_items"] == 7
    assert data["summary"]["linked_capabilities"] >= 27
    assert data["summary"]["relationship_links"] > data["summary"]["linked_capabilities"]
    assert data["summary"]["governance_only_items"] == 1
    assert data["constraints"]["runtime_claims"] is False
    assert data["constraints"]["production_certification"] is False
    assert all(item["source_anchor"] for item in data["roadmap_items"])
    assert all(item["source_sha256"] for item in data["roadmap_items"])


def test_wx10_links_all_weather_products_with_relationships():
    data = mod.build()
    row = next(item for item in data["roadmap_items"] if item["roadmap_id"] == "WX-10")
    assert row["capabilities"] == [f"WX-{index:03d}" for index in range(1, 11)]
    assert {link["relation"] for link in row["capability_links"]} >= {
        "contained_view",
        "derived_product",
        "governing_contract",
    }


def make_fixture(tmp_path: Path):
    root = tmp_path
    source = root / "docs/capability-registry/roadmap/roadmap_items.yaml"
    registry = root / "docs/capability-registry/generated/capability_registry.json"
    architecture = root / "architecture.md"
    output = root / "docs/capability-registry/generated/roadmap"
    source.parent.mkdir(parents=True)
    registry.parent.mkdir(parents=True, exist_ok=True)
    architecture.write_text("### WX-10 — CanonicalWeatherState\n", encoding="utf-8")
    registry.write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "id": "WX-001",
                        "domain": "weather",
                        "title": {"en": "Current weather"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    document = {
        "schema_version": "1.0.0",
        "source_policy": "curated_only",
        "items": [
            {
                "id": "WX-10",
                "title": "CanonicalWeatherState",
                "status": "planned",
                "source": "architecture.md",
                "source_anchor": "### WX-10 — CanonicalWeatherState",
                "capability_links": [
                    {
                        "id": "WX-001",
                        "relation": "contained_view",
                        "rationale": "Current weather is a contained canonical view.",
                    }
                ],
            }
        ],
    }
    source.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return root, source, registry, output, document


def test_validation_rejects_missing_source_anchor(tmp_path):
    root, source, registry, _, document = make_fixture(tmp_path)
    document["items"][0]["source_anchor"] = "### WX-10 — Missing"
    source.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="source_anchor not found"):
        mod.build(root=root, source_path=source, registry_path=registry)


def test_validation_rejects_unknown_capability_and_duplicate_link(tmp_path):
    root, source, registry, _, document = make_fixture(tmp_path)
    document["items"][0]["capability_links"].append(
        {
            "id": "WX-001",
            "relation": "duplicate",
            "rationale": "This duplicate must be rejected by the linker.",
        }
    )
    document["items"][0]["capability_links"].append(
        {
            "id": "WX-999",
            "relation": "unknown",
            "rationale": "This unknown capability must be rejected.",
        }
    )
    source.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        mod.build(root=root, source_path=source, registry_path=registry)
    message = str(exc.value)
    assert "duplicate capability WX-001" in message
    assert "unknown capability 'WX-999'" in message


def test_check_detects_drift_in_every_generated_surface(tmp_path):
    root, source, registry, output, _ = make_fixture(tmp_path)
    mod.generate(root=root, source_path=source, registry_path=registry, output_dir=output)
    ok, drift, _ = mod.check(
        root=root, source_path=source, registry_path=registry, output_dir=output
    )
    assert ok and drift == []

    (output / "roadmap_capability_links.csv").write_text("stale\n", encoding="utf-8")
    ok, drift, _ = mod.check(
        root=root, source_path=source, registry_path=registry, output_dir=output
    )
    assert not ok
    assert "changed:roadmap_capability_links.csv" in drift


def test_generated_paths_cannot_be_governance_scope(tmp_path):
    root, source, registry, _, document = make_fixture(tmp_path)
    generated = root / "docs/capability-registry/generated/example"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text("derived", encoding="utf-8")
    item = document["items"][0]
    item["governance_scope"] = ["docs/capability-registry/generated/example"]
    source.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="must not target generated outputs"):
        mod.build(root=root, source_path=source, registry_path=registry)
