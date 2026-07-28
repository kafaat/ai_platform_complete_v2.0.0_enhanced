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
import re
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


def test_header_env_refs_expand_and_never_smuggle_a_value(monkeypatch):
    # A token-gated endpoint is reached by declaring only the ${ENV_VAR} NAME in the
    # plan; the value is resolved from the environment at run time. An unset variable
    # expands to empty (the probe then fails its expected status) — it can never
    # smuggle a false pass, and no secret ever lives in the committed plan.
    m = _runner()
    probe = {"headers": {"X-Agent-Token": "${SAHOOL_AGENT_TOKEN}", "X-Static": "lit"}}
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "s3cr3t")
    resolved = m._resolve_headers(probe)
    assert resolved == {"X-Agent-Token": "s3cr3t", "X-Static": "lit"}
    monkeypatch.delenv("SAHOOL_AGENT_TOKEN", raising=False)
    assert m._resolve_headers(probe)["X-Agent-Token"] == ""


def test_bearer_scheme_header_expands_env_ref(monkeypatch):
    # A JWT-gated endpoint uses "Bearer ${ENV}": only the token is drawn from the
    # environment; the scheme prefix stays literal.
    m = _runner()
    probe = {"headers": {"Authorization": "Bearer ${SAHOOL_PLATFORM_PROBE_JWT}"}}
    monkeypatch.setenv("SAHOOL_PLATFORM_PROBE_JWT", "jwt.abc.def")
    assert m._resolve_headers(probe)["Authorization"] == "Bearer jwt.abc.def"


def test_committed_plans_embed_no_literal_secrets():
    # Any header that names a credential must draw its value from an ${ENV} reference,
    # never a committed literal — so a plan can target a token-gated endpoint (a bare
    # "${TOKEN}" or a "Bearer ${JWT}" scheme prefix) without embedding the secret itself.
    env_ref = re.compile(r"\$\{[A-Z0-9_]+\}")
    for path in sorted(PLAN_DIR.glob("*.json")):
        plan = json.loads(path.read_text())
        for probe in plan["probes"]:
            for name, value in (probe.get("headers") or {}).items():
                if any(k in name.lower() for k in ("token", "secret", "authorization", "api-key")):
                    assert env_ref.search(value), (
                        f"{probe['probe_id']}:{name} must reference an env var, not a literal"
                    )
