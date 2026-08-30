from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
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
harness = load(
    "runtime_verification_harness_subject_binding",
    ROOT / "scripts/ci/runtime_verification_harness.py",
)

SHA = "a" * 40
OTHER_SHA = "b" * 40
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
PLAN_HASH = "c" * 64
KEY = "runtime-evidence-test-key"
ITEM = {
    "service": "weather-service",
    "probes": [{"kind": "health", "method": "GET", "path": "/healthz"}],
}


def evidence(**updates):
    body = {
        "schema_version": "2.0",
        "service": "weather-service",
        "tested_sha": SHA,
        "environment_id": "staging-pg16",
        "base_url_sha256": "e" * 64,
        "started_at": (NOW - timedelta(seconds=1)).isoformat(),
        "completed_at": NOW.isoformat(),
        "plan_sha256": PLAN_HASH,
        "runtime_identity": {
            "service": "weather-service",
            "git_sha": SHA,
            "build_id": "build-1",
            "metadata_source": "immutable-image-file",
            "image_digest": "sha256:" + "f" * 64,
            "image_digest_source": "deployment-manifest",
        },
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
    body["attestation"] = {
        "issuer": "sahool-staging-hmac",
        "algorithm": "hmac-sha256",
    }
    body["attestation"]["signature"] = hmac.new(
        KEY.encode(), ingestion.signing_payload(body), hashlib.sha256
    ).hexdigest()
    return body


def validate(tmp_path: Path, body: dict, expected_sha: str | None = SHA):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    previous = os.environ.get("SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY")
    os.environ["SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY"] = KEY
    try:
        return ingestion.validate_evidence(
            path,
            ITEM,
            PLAN_HASH,
            expected_subject_sha=expected_sha,
            now=NOW,
        )
    finally:
        if previous is None:
            os.environ.pop("SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY", None)
        else:
            os.environ["SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY"] = previous


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


def test_recomputed_self_hash_without_signing_key_is_rejected(tmp_path):
    body = evidence()
    body["probe_results"][0]["http_status"] = 204
    body["evidence_sha256"] = ingestion.evidence_digest(body)
    result = validate(tmp_path, body)
    assert result["valid"] is False
    assert "invalid_attestation_signature" in result["errors"]


def test_untrusted_environment_cannot_set_runtime_verified(tmp_path):
    result = validate(tmp_path, evidence(environment_id="arbitrary-untrusted"))
    assert result["valid"] is False
    assert "untrusted_environment" in result["errors"]


def test_runtime_identity_must_match_subject(tmp_path):
    body = evidence()
    body["runtime_identity"]["git_sha"] = OTHER_SHA
    body["evidence_sha256"] = ingestion.evidence_digest(body)
    body["attestation"]["signature"] = hmac.new(
        KEY.encode(), ingestion.signing_payload(body), hashlib.sha256
    ).hexdigest()
    result = validate(tmp_path, body)
    assert result["valid"] is False
    assert "runtime_identity_sha_mismatch" in result["errors"]


def test_duplicate_probe_records_are_rejected(tmp_path):
    body = evidence()
    body["probe_results"].append(dict(body["probe_results"][0]))
    body["evidence_sha256"] = ingestion.evidence_digest(body)
    body["attestation"]["signature"] = hmac.new(
        KEY.encode(), ingestion.signing_payload(body), hashlib.sha256
    ).hexdigest()
    result = validate(tmp_path, body)
    assert result["valid"] is False
    assert "duplicate_probe_results" in result["errors"]


def test_harness_cannot_count_evidence_rejected_by_shared_validator(tmp_path, monkeypatch):
    body = evidence(environment_id="arbitrary-untrusted")
    (tmp_path / "weather-service.json").write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setattr(harness, "EVIDENCE_DIR", tmp_path)
    plan = {"plan_sha256": PLAN_HASH, "services": [ITEM]}
    valid, invalid = harness.evidence_validation(plan)
    assert valid == 0
    assert invalid == ["weather-service.json"]


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


def test_probe_refuses_diagnostic_only_environment():
    with pytest.raises(ValueError, match="not eligible"):
        probe.trusted_issuer("local", "sahool-staging-hmac")


def test_deployment_manifest_must_bind_image_to_subject(tmp_path):
    manifest = tmp_path / "deployment.json"
    manifest.write_text(
        json.dumps(
            {
                "services": {
                    "weather-service": {
                        "service": "weather-service",
                        "git_sha": OTHER_SHA,
                        "build_id": "build-1",
                        "image_digest": "sha256:" + "f" * 64,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not match"):
        probe.deployment_identity(manifest, "weather-service", SHA)


def test_live_runtime_identity_must_match_deployment_manifest(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps(
                {
                    "service": "weather-service",
                    "git_sha": OTHER_SHA,
                    "build_id": "build-1",
                    "metadata_source": "immutable-image-file",
                }
            ).encode()

    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    deployed = {
        "service": "weather-service",
        "git_sha": SHA,
        "build_id": "build-1",
        "image_digest": "sha256:" + "f" * 64,
    }
    with pytest.raises(ValueError, match="differs"):
        probe.runtime_identity("https://service", "/runtime-identity", 1.0, deployed)
