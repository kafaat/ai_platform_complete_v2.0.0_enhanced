from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "runtime-contracts/generated/runtime_contracts.json"
SUMMARY = ROOT / "runtime-contracts/generated/runtime_contracts_summary.json"


def _payload():
    return json.loads(INDEX.read_text(encoding="utf-8"))


def test_runtime_contracts_are_static_evidence_only():
    payload = _payload()
    assert payload["static_repository_evidence_only"] is True
    assert payload["services"]
    assert all(item["static_repository_evidence_only"] is True for item in payload["services"])


def test_runtime_contracts_are_unique_and_deterministic_shape():
    services = _payload()["services"]
    names = [item["service"] for item in services]
    assert names == sorted(names)
    assert len(names) == len(set(names))
    assert "odoo-bridge" not in names
    for item in services:
        assert set(item["endpoints"]) == {"health", "readiness", "metrics"}
        assert set(item["observability"]) == {
            "metric_names",
            "trace_spans",
            "metrics_instrumented",
            "tracing_instrumented",
        }
        assert item["completeness"]["passed"] <= item["completeness"]["total"]


def test_runtime_contract_summary_never_claims_live_verification():
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["live_runtime_verified"] == 0
    assert summary["complete_static_contracts"] <= summary["services"]


def test_secret_values_are_never_serialized():
    raw = INDEX.read_text(encoding="utf-8")
    # Registry contains only environment variable names, never assignments/values.
    for service in _payload()["services"]:
        for secret in service["secrets"]:
            assert secret.isupper()
            assert "=" not in secret
    assert "BEGIN PRIVATE KEY" not in raw
