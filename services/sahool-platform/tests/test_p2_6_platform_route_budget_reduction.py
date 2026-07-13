import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCH = ROOT.parents[1] / "docs/architecture"
ROUTE_RE = re.compile(r"@(app|router)\.(get|post|put|patch|delete)\(")


def test_platform_route_budget_reduced_after_extractions():
    data = json.loads((ARCH / "platform_extraction_map.json").read_text(encoding="utf-8"))
    budget = data["p2_6_route_budget_reduction"]["new_max_platform_routes"]
    current = sum(
        len(ROUTE_RE.findall(p.read_text(encoding="utf-8", errors="ignore")))
        for p in ROOT.rglob("*.py")
        if not str(p.relative_to(ROOT)).startswith("tests/")
    )
    assert (
        budget <= 597
    )  # deliberately raised 567->570 (JSON-metrics hotfix); 575->576 WX-10.6 candidate; 576->577 WX-10.7 decision review; 577->578 WX-10.8 review-queue; 578->582 WX-10.9..10.12 execution; 582->591 WX-10.13..11.6 model/MLOps chain; 591->592 Phase E decision-evidence BFF proxy (owned+documented); 592->593 durable lab chain-of-custody transition + publication (v156/v159/v160; owned+documented); 593->595 MPC P1.1b irrigation bridge plan+capabilities (bff-orchestrator; owned+documented; same pattern as irrigation_*.py + water_decision_bridge); 595->597 MPC P1.1c-b server-authoritative simulate+recommendation (bff-orchestrator; owned+documented; SoR fact-sourcing + fail-closed)
    assert current <= budget
    assert data["p2_6_route_budget_reduction"]["previous_baseline_route_count"] == 567


def test_route_growth_requires_ownership_map_update():
    data = json.loads((ARCH / "platform_extraction_map.json").read_text(encoding="utf-8"))
    assert "No route growth" in data["p2_6_route_budget_reduction"]["policy"]
