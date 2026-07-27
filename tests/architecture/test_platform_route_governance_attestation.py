from pathlib import Path

import pytest

from scripts.ci.platform_route_governance_attestation import (
    GENERATED_PATH,
    build_attestation,
    canonical_json,
    check_generated,
)
from scripts.ci.platform_route_ownership_guard import (
    GENERATED_PATH as OWNERSHIP_GENERATED_PATH,
)
from scripts.ci.platform_route_ownership_guard import (
    build_inventory as build_ownership_inventory,
)
from scripts.ci.platform_route_ownership_guard import (
    check_generated as check_ownership_generated,
)


def test_generated_ownership_inventory_is_current():
    inventory = build_ownership_inventory()
    check_ownership_generated(inventory, OWNERSHIP_GENERATED_PATH)
    assert inventory["counts"] == {
        "surface_routes": 634,
        "direct_routes": 630,
        "api_route_declarations": 4,
        "mapped_routes": 634,
    }


def test_attestation_cross_binds_budget_and_ownership_counts():
    attestation = build_attestation()
    statement = attestation["statement"]
    assert statement["raw_routes"] == 630
    assert statement["infrastructure_routes"] == 4
    assert statement["domain_budget_routes"] == 626
    assert statement["domain_route_budget"] == 629
    assert statement["full_ownership_surface"] == 634
    assert statement["api_route_declarations"] == 4
    assert len(attestation["statement_sha256"]) == 64


def test_generated_governance_attestation_is_current():
    attestation = build_attestation()
    check_generated(attestation, GENERATED_PATH)


def test_stale_governance_attestation_fails_closed(tmp_path: Path):
    attestation = build_attestation()
    stale = tmp_path / "attestation.json"
    stale.write_text(canonical_json({**attestation, "statement_sha256": "0" * 64}))
    with pytest.raises(AssertionError, match="stale"):
        check_generated(attestation, stale)
