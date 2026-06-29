from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_phase_runtime_workers_use_fail_closed_contracts():
    src = (ROOT / "services/sahool-platform/api/phase_runtime_workers.py").read_text(encoding="utf-8")
    contracts = (ROOT / "shared/runtime_worker_contracts.py").read_text(encoding="utf-8")
    assert "build_plugin_worker_action" in src
    assert "PLUGIN_EXECUTOR_URL" in src
    assert "MODEL_SERVING_BACKEND_URL" in src
    assert "ACTUATOR_ADAPTER_CONFIG_JSON" in src
    assert "pending_external_ack" in src
    assert "waiting_ack" in contracts
    assert "completed' if" not in src


def test_worker_contract_module_is_in_release_manifest_inputs():
    release_builder = (ROOT / "scripts/release/build_release_bundle.py").read_text(encoding="utf-8")
    assert "shared/runtime_worker_contracts.py" in release_builder
    assert "PHASE20_RUNTIME_WORKER_SIDE_EFFECTS_REPORT_20260626.md" in release_builder
