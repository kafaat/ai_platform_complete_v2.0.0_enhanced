import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/runtime_verification_harness.py"


def load_module():
    spec = importlib.util.spec_from_file_location("runtime_verification_harness", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_plan_is_fail_closed_and_never_certifies_production():
    plan, summary, _ = load_module().build()
    assert plan["fail_closed"] is True
    assert summary["production_certified_services"] == 0
    assert all(s["runtime_verified"] is False for s in plan["services"])
    assert all(s["production_certified"] is False for s in plan["services"])


def test_plan_has_integrity_hash_and_stable_service_order():
    module = load_module()
    plan, _, _ = module.build()
    core = {k: v for k, v in plan.items() if k != "plan_sha256"}
    assert plan["plan_sha256"] == module.digest(core)
    assert [s["service"] for s in plan["services"]] == sorted(
        s["service"] for s in plan["services"]
    )


def test_generated_summary_matches_plan():
    plan = json.loads((ROOT / "runtime-verification/generated/runtime_probe_plan.json").read_text())
    summary = json.loads(
        (ROOT / "runtime-verification/generated/runtime_verification_summary.json").read_text()
    )
    assert summary["services"] == len(plan["services"])
    assert summary["planned_probes"] == sum(len(s["probes"]) for s in plan["services"])
    assert summary["runtime_verified_services"] == 0
