from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "scripts/ci/runtime_identity_bridge.py"
SHA = "a" * 40
KEY = "test-secret"


def m():
    s = importlib.util.spec_from_file_location("trust_bridge_test", MOD)
    x = importlib.util.module_from_spec(s)
    s.loader.exec_module(x)
    return x


def bridge(x):
    return json.loads(x.IDENTITY_MAP.read_text())


def signed(x, service, probes, **overrides):
    b = bridge(x)
    d = x.expected_digests(b, service)
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    ev = {
        "schema_version": "2.0",
        "kind": "functional",
        "service": service,
        "tested_sha": SHA,
        "environment_id": "staging-pg16",
        "generated_at": now,
        "run_id": "run-1",
        "runtime_identity": {
            "service": service,
            "git_sha": SHA,
            "build_id": "build-1",
            "image_digest": "sha256:" + "b" * 64,
        },
        "artifact_digests": d,
        "probe_results": [{"probe_id": p, "status": "passed"} for p in probes],
    }
    ev.update(overrides)
    ev["attestation"] = {"issuer": "sahool-staging-hmac", "algorithm": "hmac-sha256"}
    ev["attestation"]["signature"] = hmac.new(
        KEY.encode(), x._canonical(ev), hashlib.sha256
    ).hexdigest()
    return ev


def evalcap(x, evs, cap="SOIL-001"):
    out = x.evaluate_propagation(bridge(x), evs, SHA, datetime.now(UTC))
    return next(v for v in out if v["capability"] == cap)


def test_two_partial_files_cannot_be_combined(monkeypatch):
    x = m()
    monkeypatch.setenv("SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY", KEY)
    a = signed(x, "soil-service", ["soil-texture-loam"])
    b = signed(x, "soil-service", ["soil-texture-sand"], run_id="run-2")
    assert not evalcap(x, {"soil-service": [a, b]})["eligible"]


def test_one_atomic_bundle_is_eligible(monkeypatch):
    x = m()
    monkeypatch.setenv("SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY", KEY)
    ev = signed(x, "soil-service", ["soil-texture-loam", "soil-texture-sand"])
    r = evalcap(x, {"soil-service": [ev]})
    assert r["eligible"] and r["run_id"] == "run-1"


def test_unsigned_evidence_rejected(monkeypatch):
    x = m()
    monkeypatch.setenv("SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY", KEY)
    ev = signed(x, "soil-service", ["soil-texture-loam", "soil-texture-sand"])
    ev.pop("attestation")
    assert "missing_fields" in evalcap(x, {"soil-service": [ev]})["reason"]


def test_untrusted_environment_rejected(monkeypatch):
    x = m()
    monkeypatch.setenv("SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY", KEY)
    ev = signed(
        x, "soil-service", ["soil-texture-loam", "soil-texture-sand"], environment_id="local"
    )
    ev["attestation"]["signature"] = hmac.new(
        KEY.encode(), x._canonical(ev), hashlib.sha256
    ).hexdigest()
    assert evalcap(x, {"soil-service": [ev]})["reason"] == "untrusted_environment"


def test_spoofed_runtime_sha_rejected(monkeypatch):
    x = m()
    monkeypatch.setenv("SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY", KEY)
    ev = signed(x, "soil-service", ["soil-texture-loam", "soil-texture-sand"])
    ev["runtime_identity"]["git_sha"] = "c" * 40
    ev["attestation"]["signature"] = hmac.new(
        KEY.encode(), x._canonical(ev), hashlib.sha256
    ).hexdigest()
    assert evalcap(x, {"soil-service": [ev]})["reason"] == "runtime_identity_mismatch"


def test_future_evidence_rejected(monkeypatch):
    x = m()
    monkeypatch.setenv("SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY", KEY)
    ts = (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    ev = signed(x, "soil-service", ["soil-texture-loam", "soil-texture-sand"], generated_at=ts)
    ev["attestation"]["signature"] = hmac.new(
        KEY.encode(), x._canonical(ev), hashlib.sha256
    ).hexdigest()
    assert evalcap(x, {"soil-service": [ev]})["reason"] == "future_dated_evidence"


def test_digest_mismatch_rejected(monkeypatch):
    x = m()
    monkeypatch.setenv("SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY", KEY)
    ev = signed(x, "soil-service", ["soil-texture-loam", "soil-texture-sand"])
    ev["artifact_digests"]["probe_plan_sha256"] = "0" * 64
    ev["attestation"]["signature"] = hmac.new(
        KEY.encode(), x._canonical(ev), hashlib.sha256
    ).hexdigest()
    assert evalcap(x, {"soil-service": [ev]})["reason"] == "artifact_digest_mismatch"


def test_duplicate_and_unknown_probe_ids_rejected(monkeypatch):
    x = m()
    monkeypatch.setenv("SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY", KEY)
    ev = signed(x, "soil-service", ["soil-texture-loam", "soil-texture-loam"])
    assert evalcap(x, {"soil-service": [ev]})["reason"] == "duplicate_probe_id"
    ev = signed(x, "soil-service", ["soil-texture-loam", "unknown"])
    assert evalcap(x, {"soil-service": [ev]})["reason"] == "unknown_probe_id"


def test_bad_signature_rejected(monkeypatch):
    x = m()
    monkeypatch.setenv("SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY", KEY)
    ev = signed(x, "soil-service", ["soil-texture-loam", "soil-texture-sand"])
    ev["attestation"]["signature"] = "0" * 64
    assert evalcap(x, {"soil-service": [ev]})["reason"] == "invalid_attestation_signature"


def test_corrupt_evidence_is_reported(tmp_path, monkeypatch):
    x = m()
    d = tmp_path / "evidence"
    d.mkdir()
    (d / "bad.json").write_text("{")
    monkeypatch.setattr(x, "FUNCTIONAL_EVIDENCE_DIR", d)
    loaded, errors = x.load_committed_evidence()
    assert loaded == {} and errors and "corrupt evidence" in errors[0]


def test_missing_authoritative_registry_fails_closed(monkeypatch):
    x = m()
    monkeypatch.setattr(x, "PROBE_PLAN", Path("/does/not/exist"))
    assert any(
        "authoritative runtime probe plan missing" in e for e in x.validate_identity_map(bridge(x))
    )
