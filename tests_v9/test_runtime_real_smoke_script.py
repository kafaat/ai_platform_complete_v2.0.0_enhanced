from pathlib import Path


def test_runtime_real_smoke_script_has_core_guards():
    text = Path("scripts/ci/runtime_real_smoke.sh").read_text(encoding="utf-8")
    required = [
        "production_honesty_guard.py",
        "internal_graphql_security_guard.py",
        "health_readiness_schema_guard.py",
        "contract_capabilities_schema_guard.py",
        "route_residual_classification_guard.py",
        "production_evidence_pack_guard.py",
        "edge_model_contract_guard.py",
        "runtime_real_smoke_ok",
    ]
    missing = [item for item in required if item not in text]
    assert not missing, f"runtime smoke script missing: {missing}"
