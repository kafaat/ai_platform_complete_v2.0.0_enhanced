import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
ARCH = REPO / "docs/architecture"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ci.platform_route_classification import (  # noqa: E402
    INFRASTRUCTURE_ROUTES,
    RouteDeclaration,
    assert_infrastructure_allowlist_is_used,
    collect_platform_routes,
    extract_routes,
    is_infrastructure_route,
    normalize_route_path,
    partition_routes,
)


def _inventory():
    raw = collect_platform_routes(ROOT)
    assert_infrastructure_allowlist_is_used(raw)
    infrastructure, domain = partition_routes(raw)
    return raw, infrastructure, domain


def test_platform_domain_route_budget_remains_unchanged_after_infra_exclusion():
    data = json.loads((ARCH / "platform_extraction_map.json").read_text(encoding="utf-8"))
    policy = data["p2_6_route_budget_reduction"]
    budget = policy["domain_route_budget"]
    raw, infrastructure, domain = _inventory()

    assert budget == policy["new_max_platform_routes"] == 629
    assert len(raw) == 631
    assert len(infrastructure) == 4
    assert len(domain) == 627
    assert len(raw) == len(infrastructure) + len(domain)
    assert len(domain) <= budget, (
        "Platform domain-route budget exceeded:\n"
        f"  raw routes:            {len(raw)}\n"
        f"  infrastructure routes: {len(infrastructure)}\n"
        f"  domain routes:         {len(domain)}\n"
        f"  domain maximum:        {budget}\n"
    )
    assert any(r.key == ("GET", "/runtime-identity") for r in raw)
    assert any(r.key == ("GET", "/runtime-identity") for r in infrastructure)


def test_canonical_infrastructure_allowlist_matches_documented_policy():
    data = json.loads((ARCH / "platform_extraction_map.json").read_text(encoding="utf-8"))
    documented = {
        (item["method"], item["path"])
        for item in data["p2_6_route_budget_reduction"]["infrastructure_route_allowlist"]
    }
    assert documented == set(INFRASTRUCTURE_ROUTES)


def test_only_exact_runtime_identity_get_is_infrastructure():
    assert ("GET", "/runtime-identity") in INFRASTRUCTURE_ROUTES
    assert ("POST", "/runtime-identity") not in INFRASTRUCTURE_ROUTES
    assert ("GET", "/fields/runtime-identity") not in INFRASTRUCTURE_ROUTES
    assert ("GET", "/runtime-identity/export") not in INFRASTRUCTURE_ROUTES
    assert ("GET", "/runtime-identity-v2") not in INFRASTRUCTURE_ROUTES
    assert is_infrastructure_route("get", "//runtime-identity/")


def test_similarly_named_routes_remain_in_domain_partition():
    routes = [
        RouteDeclaration("GET", "/runtime-identity", "x.py", 1, "infra"),
        RouteDeclaration("GET", "/fields/runtime-identity", "x.py", 2, "field"),
        RouteDeclaration("GET", "/runtime-identity/export", "x.py", 3, "export"),
        RouteDeclaration("POST", "/runtime-identity", "x.py", 4, "post"),
    ]
    infrastructure, domain = partition_routes(routes)
    assert [r.function for r in infrastructure] == ["infra"]
    assert {r.function for r in domain} == {"field", "export", "post"}


def test_route_path_normalization_is_conservative():
    assert normalize_route_path("runtime-identity") == "/runtime-identity"
    assert normalize_route_path("/runtime-identity/") == "/runtime-identity"
    assert normalize_route_path("//runtime-identity") == "/runtime-identity"
    assert normalize_route_path("/Runtime-Identity") == "/Runtime-Identity"
    assert normalize_route_path("/runtime%2Didentity") == "/runtime%2Didentity"


def test_non_literal_route_path_fails_closed(tmp_path: Path):
    source = tmp_path / "routes.py"
    source.write_text(
        'PATH = "/runtime-identity"\n@app.get(PATH)\ndef route():\n    pass\n',
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="Non-literal route path"):
        extract_routes(source)


def test_route_declaration_retains_source_and_line(tmp_path: Path):
    source = tmp_path / "routes.py"
    source.write_text('@app.get("/x")\ndef route():\n    pass\n', encoding="utf-8")
    [route] = extract_routes(source)
    assert route.method == "GET"
    assert route.path == "/x"
    assert route.line == 1
    assert route.source.endswith("routes.py")


def test_unused_infrastructure_allowlist_entries_fail():
    raw, _, _ = _inventory()
    declared = {route.key for route in raw}
    assert INFRASTRUCTURE_ROUTES <= declared
    assert_infrastructure_allowlist_is_used(raw)


def test_unused_allowlist_guard_rejects_incomplete_inventory():
    with pytest.raises(AssertionError, match="not declared"):
        assert_infrastructure_allowlist_is_used(
            [RouteDeclaration("GET", "/runtime-identity", "x.py", 1, "identity")]
        )


def test_route_growth_requires_ownership_map_update():
    data = json.loads((ARCH / "platform_extraction_map.json").read_text(encoding="utf-8"))
    policy = data["p2_6_route_budget_reduction"]
    assert "No platform domain-route growth" in policy["policy"]
    assert "explicit method-and-normalized-path allowlist" in policy["infrastructure_budget_policy"]
