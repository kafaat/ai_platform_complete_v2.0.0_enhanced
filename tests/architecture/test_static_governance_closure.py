from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/static_governance_closure.py"


def load_module():
    spec = importlib.util.spec_from_file_location("static_governance_closure", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_closure_scope_never_claims_runtime_or_production():
    module = load_module()
    payload = module.closure_payload([], {"passed": True}, {})
    assert payload["runtime_verified"] is False
    assert payload["production_certified"] is False


def test_closure_requires_every_check_and_test_to_pass():
    module = load_module()
    closed = module.closure_payload([{"passed": True}], {"passed": True}, {})
    open_check = module.closure_payload([{"passed": False}], {"passed": True}, {})
    open_test = module.closure_payload([{"passed": True}], {"passed": False}, {})
    assert closed["status"] == "CLOSED"
    assert open_check["status"] == "OPEN"
    assert open_test["status"] == "OPEN"


def test_manifest_is_sorted_and_excludes_closure_self_hashes():
    module = load_module()
    paths = [p.relative_to(ROOT).as_posix() for p in module.artifact_files()]
    assert paths == sorted(paths)
    assert all(not path.startswith("governance/generated/") for path in paths)
