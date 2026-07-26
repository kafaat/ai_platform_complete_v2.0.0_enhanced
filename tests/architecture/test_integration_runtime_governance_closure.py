from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/integration_runtime_governance_closure.py"


def load_module():
    spec = importlib.util.spec_from_file_location("integration_runtime_governance_closure", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_closure_never_claims_runtime_or_production():
    module = load_module()
    payload = module.closure_payload([])
    assert payload["runtime_verified"] is False
    assert payload["production_certified"] is False


def test_closure_requires_all_checks():
    module = load_module()
    assert module.closure_payload([{"passed": True}])["status"] == "CLOSED"
    assert module.closure_payload([{"passed": False}])["status"] == "OPEN"


def test_manifest_is_sorted_and_excludes_path2_self_hashes():
    module = load_module()
    paths = [path.relative_to(ROOT).as_posix() for path in module.artifact_files()]
    assert paths == sorted(paths)
    assert all(not path.startswith("governance/path2-generated/") for path in paths)


def test_committed_closure_evaluates_closed():
    module = load_module()
    checks, _ = module.evaluate()
    payload = module.closure_payload(checks)
    assert payload["status"] == "CLOSED"
    assert all(item["passed"] for item in checks)
