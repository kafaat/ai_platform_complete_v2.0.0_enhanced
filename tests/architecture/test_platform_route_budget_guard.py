from pathlib import Path

import pytest

from scripts.ci.platform_route_budget_guard import (
    GENERATED_PATH,
    build_inventory,
    canonical_json,
    check_generated,
)


def test_guard_reports_separate_raw_infrastructure_and_domain_counts():
    inventory = build_inventory()
    counts = inventory["counts"]
    assert counts == {
        "raw_routes": 630,
        "infrastructure_routes": 4,
        "domain_budget_routes": 626,
        "domain_route_budget": 629,
        "domain_budget_headroom": 3,
    }


def test_generated_route_budget_inventory_is_current():
    inventory = build_inventory()
    check_generated(inventory, GENERATED_PATH)


def test_generated_inventory_contains_runtime_identity_as_infrastructure():
    inventory = build_inventory()
    rows = [
        row
        for row in inventory["routes"]
        if row["method"] == "GET" and row["path"] == "/runtime-identity"
    ]
    assert len(rows) == 1
    assert rows[0]["classification"] == "infrastructure"


def test_generated_inventory_drift_fails_closed(tmp_path: Path):
    inventory = build_inventory()
    stale = tmp_path / "inventory.json"
    stale.write_text(canonical_json({**inventory, "inventory_sha256": "0" * 64}))
    with pytest.raises(AssertionError, match="stale"):
        check_generated(inventory, stale)
