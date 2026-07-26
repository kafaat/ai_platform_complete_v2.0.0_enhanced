from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/runtime_evidence_ingestion.py"


def load_module():
    spec = importlib.util.spec_from_file_location("runtime_evidence_ingestion", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ledger_is_fail_closed_and_has_no_static_runtime_claims():
    data = json.loads(
        (ROOT / "runtime-verification/generated/runtime_evidence_ledger.json").read_text()
    )
    assert data["fail_closed"] is True
    assert all(not service["runtime_verified"] for service in data["services"])
    assert all(not service["production_certified"] for service in data["services"])


def test_ledger_hash_is_stable():
    module = load_module()
    ledger, _ = module.build()
    core = {key: value for key, value in ledger.items() if key != "ledger_sha256"}
    assert ledger["ledger_sha256"] == module.sha256_bytes(module.canonical(core).encode())


def test_evidence_validator_requires_exact_probe_set(tmp_path):
    module = load_module()
    item = {"service": "svc", "probes": [{"kind": "health", "method": "GET", "path": "/healthz"}]}
    path = tmp_path / "svc.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "service": "svc",
                "tested_sha": "abcdef1",
                "environment_id": "test",
                "started_at": "2026-01-01T00:00:00+00:00",
                "completed_at": "2026-01-01T00:00:01+00:00",
                "plan_sha256": "p",
                "probe_results": [],
            }
        )
    )
    result = module.validate_evidence(path, item, "p")
    assert result["valid"] is False
    assert "missing_probe_results" in result["errors"]
    assert "probe_set_mismatch" in result["errors"]
