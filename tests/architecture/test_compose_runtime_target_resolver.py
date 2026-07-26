from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/compose_runtime_target_resolver.py"


def load_module():
    spec = importlib.util.spec_from_file_location("compose_runtime_target_resolver", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_resolver_is_fail_closed_and_never_claims_runtime_truth():
    payload, _, _ = load_module().build()
    assert payload["fail_closed"] is True
    assert payload["runtime_verified"] is False
    assert payload["production_certified"] is False
    assert all(row["runtime_verified"] is False for row in payload["targets"])


def test_resolved_targets_use_internal_compose_dns():
    payload, env, _ = load_module().build()
    resolved = [row for row in payload["targets"] if row["resolved"]]
    assert resolved
    for row in resolved:
        urls = [member["base_url"] for member in row.get("members", [])] or [row["base_url"]]
        assert all(url.startswith("http://") for url in urls)
    assert "localhost" not in env
    assert "127.0.0.1" not in env


def test_unresolved_targets_are_explicit_not_silently_dropped():
    payload, _, _ = load_module().build()
    planned = json.loads(
        (ROOT / "runtime-verification/generated/runtime_probe_plan.json").read_text()
    )
    expected = sum(1 for row in planned["services"] if row.get("probes"))
    assert len(payload["targets"]) == expected
    assert all(row["resolved"] for row in payload["targets"])
    mcp = next(row for row in payload["targets"] if row["service"] == "mcp_servers")
    assert len(mcp["members"]) == 4


def test_generated_artifacts_match():
    module = load_module()
    payload, env, report = module.build()
    assert json.loads(module.OUT_JSON.read_text()) == payload
    assert module.OUT_ENV.read_text() == env
    assert module.OUT_MD.read_text() == report
