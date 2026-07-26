import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/route_conflict_guard.py"
OUT = ROOT / "execution-audit/generated/route_conflicts.json"


def load_module():
    spec = importlib.util.spec_from_file_location("route_conflict_guard", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_generated_route_conflicts_are_current():
    mod = load_module()
    assert OUT.read_text(encoding="utf-8") == mod.render(mod.build_payload())


def test_no_hard_same_scope_route_conflicts():
    payload = json.loads(OUT.read_text(encoding="utf-8"))
    assert payload["hard_conflict_count"] == 0
    assert payload["hard_conflicts"] == []


def test_static_evidence_does_not_claim_runtime_proof():
    payload = json.loads(OUT.read_text(encoding="utf-8"))
    assert payload["analysis_kind"] == "static_repository_evidence"
    assert payload["runtime_verified"] is False
    assert payload["production_certified"] is False
