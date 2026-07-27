"""Guards for the standalone functional-probe layer (weather-service).

These tests are STATIC — they never boot a service. They assert that:
  1. every functional probe plan is structurally valid;
  2. every probe points at a route the target service actually registers;
  3. the layer stays honest — a plan alone declares no runtime_verified and only
     self-contained compute probes are allowed.
Producing live functional evidence and setting runtime_verified is a separate,
reviewed step and is intentionally NOT exercised here.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN_DIR = ROOT / "runtime-verification" / "functional_probes"
RUNNER = ROOT / "scripts/ci/functional_probe_runner.py"


def _runner():
    spec = importlib.util.spec_from_file_location("functional_probe_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plans_exist_and_validate_statically():
    m = _runner()
    plans = sorted(PLAN_DIR.glob("*.json"))
    assert plans, "expected at least one functional probe plan"
    for path in plans:
        errors = m.validate_plan(json.loads(path.read_text()), path)
        assert errors == [], f"{path.name}: {errors}"


def test_check_mode_passes():
    m = _runner()
    assert m.cmd_check() == 0


def test_every_probe_targets_a_registered_route():
    m = _runner()
    for path in sorted(PLAN_DIR.glob("*.json")):
        plan = json.loads(path.read_text())
        routes = m.registered_routes(ROOT / plan["entrypoint"])
        assert routes, f"{plan['entrypoint']}: no routes parsed"
        for probe in plan["probes"]:
            key = (str(probe["method"]).upper(), probe["path"])
            assert key in routes, f"{plan['service']}: {key} not registered"


def test_layer_is_honest_compute_only_and_no_runtime_claim():
    # The plan is a specification, not evidence: it must not carry a runtime_verified
    # claim, and every probe must be self-contained compute (no DB/Redis/provider),
    # so a run needs no infrastructure and cannot smuggle a weaker claim.
    for path in sorted(PLAN_DIR.glob("*.json")):
        plan = json.loads(path.read_text())
        assert "runtime_verified" not in plan
        assert "production_certified" not in plan
        for probe in plan["probes"]:
            assert probe["dependency_class"] == "compute-only", probe["probe_id"]


def test_assertions_are_falsifiable():
    # Each probe must carry at least one response assertion — a functional probe with
    # no assertion would degrade into a liveness check, which is exactly what this
    # layer exists to be stronger than.
    for path in sorted(PLAN_DIR.glob("*.json")):
        plan = json.loads(path.read_text())
        for probe in plan["probes"]:
            assert probe.get("response_assertions"), f"{probe['probe_id']}: no assertions"
