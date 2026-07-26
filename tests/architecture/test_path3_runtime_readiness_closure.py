from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/path3_runtime_readiness_closure.py"


def load_module():
    spec = importlib.util.spec_from_file_location("path3_runtime_readiness_closure", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_path3_static_readiness_is_closed_without_runtime_claims():
    payload, _ = load_module().build()
    assert payload["closed"] is True
    assert payload["resolved_services"] == payload["planned_services"]
    assert payload["runtime_verified_services"] == 0
    assert payload["production_certified_services"] == 0


def test_mcp_and_model_lifecycle_are_explicit():
    payload, _ = load_module().build()
    assert payload["fanout_targets"]["mcp_servers"] == 4
    assert "model-lifecycle" in payload["required_profiles"]["model-registry-adapter"]


def test_generated_closure_matches():
    module = load_module()
    payload, report = module.build()
    assert json.loads(module.OUT_JSON.read_text()) == payload
    assert module.OUT_MD.read_text() == report
