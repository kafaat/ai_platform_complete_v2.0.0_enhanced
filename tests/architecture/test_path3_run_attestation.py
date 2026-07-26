from __future__ import annotations

import importlib.util
import json
import os
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/path3_run_attestation.py"


def load_module():
    spec = importlib.util.spec_from_file_location("path3_run_attestation", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_attestation_signature_detects_tampering(monkeypatch, tmp_path):
    module = load_module()
    monkeypatch.setenv("PATH3_ATTESTATION_KEY", "k" * 32)
    core = {
        "schema_version": "1.0",
        "signature_algorithm": "HMAC-SHA256",
        "run_id": "run-1",
        "tested_sha": "abcdef1",
        "environment_id": "test",
        "created_at": "2026-01-01T00:00:00+00:00",
        "plan_sha256": json.loads(module.PLAN.read_text())["plan_sha256"],
        "targets_file_sha256": module.sha256_file(module.TARGETS),
        "compose_config_sha256": "a" * 64,
        "compose_images_output_sha256": "b" * 64,
        "selected_services": [],
        "evidence_files": [],
        "fail_closed": True,
        "production_certified": False,
    }
    payload = {**core, "signature": module.sign(core)}
    assert "invalid_signature" not in module.verify_payload(payload)
    payload["tested_sha"] = "deadbeef"
    assert "invalid_signature" in module.verify_payload(payload)


def test_signing_key_is_fail_closed(monkeypatch):
    module = load_module()
    monkeypatch.delenv("PATH3_ATTESTATION_KEY", raising=False)
    try:
        module.sign({"x": 1})
    except ValueError as exc:
        assert "at least 32" in str(exc)
    else:
        raise AssertionError("short/missing signing key must be rejected")
