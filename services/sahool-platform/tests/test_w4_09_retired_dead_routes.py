"""W4-09 (routes-10): six provably dead platform routes are retired and stay retired.

The domain-route budget sat at 629/629. These six routes had no caller anywhere in the
tree (frontend, mobile, services, shared, sdk, scripts, nginx/gateway configs), no test
exercising them as product behaviour, and no entry in a capability registry. They were
removed and the ceiling was lowered by the same six (629 -> 623).

W4-09 continued (owner decision 2026-11-16) retired six more caller-less service-token routes
on the phase10 learning and phase11 federation routers, and kept the ceiling at 623 so the
domain margin is positive again (617 <= 623). Their pure functions stay in shared/ with their
own tests, and each router's /cycle still runs them.

The 2026-11-27 inspection-delivery continuation retires three more service-token
wrappers with no measured in-repository HTTP consumer: feature registration, online
materialization, and federation event-envelope construction. The first two were
listed by a Phase6 presence-only contract; their retirement is explicit there.
Their shared functions remain used by /cycle, whose inputs are not claimed to be
an identical replacement for every wrapper option. No production access-log or
external-client absence is inferred. The three new inspection BFF routes consume
the recovered slots, keeping the broader ownership budget at 623, with no margin.

GET /api/v1/registry/{workflows,indices,events} were also caller-less but stay: they are the
only executable root of their modules under platform_module_reachability_guard.

This test fails if any of them comes back without a budget decision, or if the ceiling
is raised above the W4-09 value instead of a route being placed in its owner service.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.ci.platform_route_classification import collect_platform_routes  # noqa: E402

W4_09_CEILING = 623

RETIRED = {
    ("GET", "/api/v1/registry/report-fields", "api/routers/registry.py"),
    ("GET", "/api/v1/registry/device-types", "api/routers/registry.py"),
    ("GET", "/api/v1/registry/data-quality-rules", "api/routers/registry.py"),
    ("POST", "/feature-schema", "api/phase10_continuous_learning.py"),
    ("POST", "/online-update", "api/phase10_continuous_learning.py"),
    ("POST", "/experiments/evaluate", "api/phase10_continuous_learning.py"),
    # W4-09 continued (2026-11-16).
    ("POST", "/drift", "api/phase10_continuous_learning.py"),
    ("POST", "/retraining/plan", "api/phase10_continuous_learning.py"),
    ("POST", "/champion-challenger", "api/phase10_continuous_learning.py"),
    ("POST", "/agents/propose", "api/phase11_federated_agents.py"),
    ("POST", "/experiments/shadow", "api/phase11_federated_agents.py"),
    ("POST", "/runtime/reputation/update", "api/phase11_federated_agents.py"),
    # Inspection-delivery continuation (2026-11-27); pure cycle functions remain.
    ("POST", "/feature-store/register", "api/phase10_continuous_learning.py"),
    ("POST", "/feature-store/online-materialization", "api/phase10_continuous_learning.py"),
    ("POST", "/runtime/event-envelope", "api/phase11_federated_agents.py"),
}


def test_retired_routes_are_not_declared_anywhere_in_the_platform():
    declared = {(r.method, r.path, r.source) for r in collect_platform_routes(ROOT)}
    back = sorted(RETIRED & declared)
    assert not back, (
        f"W4-09 retired routes are declared again: {back}. Re-adding one needs a budget "
        "decision in platform_extraction_map.json, or place it in its owner service."
    )
    # The same paths must not reappear under another file of the platform either.
    paths = {(m, p) for m, p, _ in RETIRED}
    moved = sorted(
        (r.method, r.path, r.source)
        for r in collect_platform_routes(ROOT)
        if (r.method, r.path) in paths
    )
    assert not moved, f"W4-09 retired routes re-declared in another platform file: {moved}"


def test_the_kept_registry_route_is_still_declared():
    declared = {(r.method, r.path) for r in collect_platform_routes(ROOT)}
    assert ("GET", "/api/v1/registry/cost-profiles") in declared, (
        "cost-profiles is listed in the capability registry and must not be retired with its siblings"
    )


def test_the_domain_ceiling_never_rises_above_the_w4_09_value():
    data = json.loads(
        (REPO / "docs/architecture/platform_extraction_map.json").read_text(encoding="utf-8")
    )
    policy = data["p2_6_route_budget_reduction"]
    assert policy["domain_route_budget"] <= W4_09_CEILING, (
        f"domain_route_budget {policy['domain_route_budget']} is above the W4-09 ceiling {W4_09_CEILING}; "
        "the ratchet only goes down"
    )
    assert policy["new_max_platform_routes"] == policy["domain_route_budget"], (
        "new_max_platform_routes must stay an exact alias of domain_route_budget"
    )
    assert "w4_09_dead_route_retirement_note" in policy, "the W4-09 lowering must stay documented"


def test_retired_phase10_routes_answer_404_on_the_live_router():
    os.environ.setdefault("SAHOOL_AGENT_TOKEN", "test-agent-token")
    from api.phase10_continuous_learning import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, headers={"X-Agent-Token": os.environ["SAHOOL_AGENT_TOKEN"]})
    for path in (
        "/feature-schema",
        "/online-update",
        "/experiments/evaluate",
        "/drift",
        "/retraining/plan",
        "/champion-challenger",
        "/feature-store/register",
        "/feature-store/online-materialization",
    ):
        res = client.post(f"/v1/phase10/learning{path}", json={"records": []})
        assert res.status_code == 404, f"{path} still served: HTTP {res.status_code}"
    # Positive control: a kept sibling on the same router is still served.
    kept = client.post("/v1/phase10/learning/dataset", json={"records": []})
    assert kept.status_code != 404, f"/dataset must remain served, got HTTP {kept.status_code}"


def test_retired_phase11_routes_answer_404_on_the_live_router():
    os.environ.setdefault("SAHOOL_AGENT_TOKEN", "test-agent-token")
    from api.phase11_federated_agents import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, headers={"X-Agent-Token": os.environ["SAHOOL_AGENT_TOKEN"]})
    for path in (
        "/agents/propose",
        "/experiments/shadow",
        "/runtime/reputation/update",
        "/runtime/event-envelope",
    ):
        res = client.post(f"/v1/phase11/federation{path}", json={})
        assert res.status_code == 404, f"{path} still served: HTTP {res.status_code}"
    # Positive control: a kept sibling on the same router is still served (422 on an empty
    # body proves the route matched).
    kept = client.post("/v1/phase11/federation/consensus", json={})
    assert kept.status_code != 404, f"/consensus must remain served, got HTTP {kept.status_code}"
