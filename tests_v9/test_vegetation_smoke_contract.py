"""Keep the independent container acceptance inventory complete and fail closed."""

import ast
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "vegetation_smoke", ROOT / "scripts/ci/vegetation_smoke.py"
)
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)
CONTRACT = json.loads((ROOT / "scripts/ci/vegetation_smoke_contract.json").read_text())
pytestmark = pytest.mark.unit


def test_external_inventory_covers_all_source_routers_and_route_methods():
    expected = {}
    modules = set()
    for path in (ROOT / "services/vegetation-analysis-service/routers").glob("*.py"):
        if path.name == "__init__.py":
            continue
        modules.add(f"routers.{path.stem}")
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != "router":
                continue
            if node.func.attr not in {"get", "post", "put", "patch", "delete"}:
                continue
            route = re.sub(r"\{([^}:]+):[^}]+\}", r"{\1}", ast.literal_eval(node.args[0]))
            expected.setdefault(route, []).append(node.func.attr)
    assert expected == CONTRACT["routes"], "Review the external inventory when changing API routes"
    assert modules == {m for m in CONTRACT["imports"] if m.startswith("routers.")}


def test_runtime_contract_rejects_whole_missing_router_and_wrong_http_method():
    schema = {"paths": {p: {m: {} for m in methods} for p, methods in CONTRACT["routes"].items()}}
    smoke.check_routes(schema, CONTRACT["routes"])
    del schema["paths"][smoke.WEEKLY]
    with pytest.raises(AssertionError, match="weekly-field-insights"):
        smoke.check_routes(schema, CONTRACT["routes"])
    schema["paths"][smoke.WEEKLY] = {"get": {}}
    with pytest.raises(AssertionError, match="POST"):
        smoke.check_routes(schema, CONTRACT["routes"])
