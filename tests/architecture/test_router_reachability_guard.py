import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/router_reachability_guard.py"
ARTIFACT = ROOT / "execution-audit/generated/router_reachability.json"


def load_module():
    spec = importlib.util.spec_from_file_location("router_reachability_guard", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_generated_artifact_matches_repository():
    module = load_module()
    assert json.loads(ARTIFACT.read_text(encoding="utf-8")) == module.build_payload()


def test_static_analysis_never_claims_runtime_or_safe_deletion():
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert payload["runtime_verified"] is False
    assert payload["production_certified"] is False
    assert payload["safe_automatic_deletions"] == 0
    assert all(item["safe_to_delete"] is False for item in payload["orphan_candidates"])


def test_reachable_nodes_reference_known_definitions():
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    known = {item["node_id"] for item in payload["definitions"]}
    assert set(payload["application_roots"]) <= known
    for edge in payload["include_edges"]:
        if edge["resolved"]:
            assert edge["source"] in known
            assert edge["target"] in known
