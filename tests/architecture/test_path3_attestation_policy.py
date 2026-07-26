from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/path3_attestation_policy.py"


def load_module():
    spec = importlib.util.spec_from_file_location("path3_attestation_policy", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload(created_at: datetime):
    return {
        "run_id": "run-12345678",
        "tested_sha": "abcdef1234",
        "environment_id": "staging",
        "created_at": created_at.isoformat(),
        "signature": "a" * 64,
    }


def test_expired_attestation_is_rejected(tmp_path):
    m = load_module()
    now = datetime(2026, 7, 26, tzinfo=UTC)
    p = payload(now - timedelta(days=2))
    rev = tmp_path / "revocations.json"
    rev.write_text('{"schema_version":"1.0","revocations":[]}')
    assert "attestation_expired" in m.evaluate(
        p, now=now, max_age_seconds=86400, revocations_path=rev
    )


def test_revoked_attestation_is_rejected(tmp_path):
    m = load_module()
    now = datetime(2026, 7, 26, tzinfo=UTC)
    p = payload(now)
    rev = tmp_path / "revocations.json"
    rev.write_text('{"schema_version":"1.0","revocations":[{"run_id":"run-12345678"}]}')
    assert "attestation_revoked" in m.evaluate(p, now=now, revocations_path=rev)


def test_environment_mismatch_is_rejected(tmp_path):
    m = load_module()
    now = datetime(2026, 7, 26, tzinfo=UTC)
    p = payload(now)
    rev = tmp_path / "revocations.json"
    rev.write_text('{"schema_version":"1.0","revocations":[]}')
    assert "environment_promotion_mismatch" in m.evaluate(
        p, now=now, revocations_path=rev, target_environment="production"
    )


def test_promotion_record_never_certifies_production():
    m = load_module()
    p = payload(datetime.now(UTC))
    record = m.promotion_record(p, "staging")
    assert record["production_certified"] is False
    assert record["promotion_scope"] == "runtime_evidence_only"
