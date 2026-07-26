from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "runtime_environment_preflight.py"


def load_module():
    spec = importlib.util.spec_from_file_location("runtime_environment_preflight", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_never_claims_runtime_truth():
    module = load_module()
    payload, _ = module.build()
    assert payload["runtime_verified"] is False
    assert payload["production_certified"] is False


def test_blocked_state_has_explicit_blockers():
    module = load_module()
    payload, _ = module.build()
    if not payload["runnable"]:
        assert payload["state"] == "BLOCKED_ENVIRONMENT"
        assert payload["blockers"]


def test_generated_artifact_matches_current_environment():
    module = load_module()
    stored = json.loads(module.OUT_JSON.read_text(encoding="utf-8"))
    current, _ = module.build()
    assert module.normalized(stored) == module.normalized(current)
