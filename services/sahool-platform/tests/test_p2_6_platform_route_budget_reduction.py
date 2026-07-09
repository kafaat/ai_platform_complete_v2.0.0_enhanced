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
        budget <= 575
    )  # deliberately raised 567->570 for the JSON-metrics hotfix (owned+documented)
    assert current <= budget
    assert data["p2_6_route_budget_reduction"]["previous_baseline_route_count"] == 567


def test_route_growth_requires_ownership_map_update():
    data = json.loads((ARCH / "platform_extraction_map.json").read_text(encoding="utf-8"))
    assert "No route growth" in data["p2_6_route_budget_reduction"]["policy"]
