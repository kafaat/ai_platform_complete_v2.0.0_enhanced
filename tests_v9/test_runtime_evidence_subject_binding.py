from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ingestion = load(
    "runtime_evidence_ingestion_subject_binding",
    ROOT / "scripts/ci/runtime_evidence_ingestion.py",
)
probe = load("runtime_probe_subject_binding", ROOT / "scripts/ci/runtime_probe.py")

SHA = "a" * 40
OTHER_SHA = "b" * 40
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
PLAN_HASH = "c" * 64
ITEM = {
    "service": "weather-service",
    "probes": [{"kind": "health", "method": "GET", "path": "/healthz"}],
}


def evidence(**updates):
    body = {
        "schema_version": "1.0",
        "service": "weather-service",
        "tested_sha": SHA,
        "environment_id": "staging-pg16",
        "started_at": (NOW - timedelta(seconds=1)).isoformat(),
        "completed_at": NOW.isoformat(),
        "plan_sha256": PLAN_HASH,
        "probe_results": [
            {
                "kind": "health",
                "method": "GET",
                "path": "/healthz",
                "status": "passed",
                "http_status": 200,
                "latency_ms": 2.5,
                "response_sha256": "d" * 64,
            }
        ],
    }
    body.update(updates)
    body["evidence_sha256"] = ingestion.evidence_digest(body)
    return body


def validate(tmp_path: Path, body: dict, expected_sha: str | None = SHA):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return ingestion.validate_evidence(
        path,
        ITEM,
        PLAN_HASH,
        expected_subject_sha=expected_sha,
        now=NOW,
    )


def test_fresh_exact_subject_bound_evidence_passes(tmp_path):
    result = validate(tmp_path, evidence())
    assert result["valid"] is True
    assert result["errors"] == []


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (evidence(tested_sha="a" * 7), "invalid_tested_sha"),
        (evidence(tested_sha=OTHER_SHA), "tested_sha_mismatch"),
        (
            evidence(
                started_at=(NOW - timedelta(hours=25, seconds=1)).isoformat(),
                completed_at=(NOW - timedelta(hours=25)).isoformat(),
            ),
            "stale_evidence",
        ),
        (
            evidence(completed_at=(NOW + timedelta(minutes=6)).isoformat()),
            "evidence_from_future",
        ),
        (evidence(environment_id="../staging"), "invalid_environment_id"),
    ],
)
def test_unbound_or_non_live_evidence_is_rejected(tmp_path, body, expected):
    result = validate(tmp_path, body)
    assert result["valid"] is False
    assert expected in result["errors"]


def test_missing_checkout_subject_fails_closed(tmp_path):
    result = validate(tmp_path, evidence(), expected_sha=None)
    assert result["valid"] is False
    assert "subject_sha_unavailable" in result["errors"]


def test_tampering_after_seal_is_rejected(tmp_path):
    body = evidence()
    body["probe_results"][0]["http_status"] = 204
    result = validate(tmp_path, body)
    assert result["valid"] is False
    assert "evidence_digest_mismatch" in result["errors"]


def test_probe_subject_defaults_to_real_checkout(monkeypatch):
    monkeypatch.setattr(probe, "checkout_sha", lambda: SHA)
    monkeypatch.delenv("TESTED_SHA", raising=False)
    assert probe.git_sha() == SHA


@pytest.mark.parametrize("claimed", ["a" * 7, OTHER_SHA, "A" * 40])
def test_probe_rejects_unbound_tested_sha(monkeypatch, claimed):
    monkeypatch.setattr(probe, "checkout_sha", lambda: SHA)
    monkeypatch.setenv("TESTED_SHA", claimed)
    with pytest.raises(ValueError):
        probe.git_sha()


def test_probe_and_ingestion_use_identical_digest_contract():
    body = evidence()
    assert probe.evidence_digest(body) == ingestion.evidence_digest(body)
