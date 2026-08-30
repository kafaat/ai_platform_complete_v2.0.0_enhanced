from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(rel, name):
    s = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def test_receipt_validation_binds_bundle_and_source():
    m = load("scripts/ci/provenance_receipt.py", "receipt_test")
    o = {
        "schema_version": "1.0",
        "verification_result": "verified",
        "verifier": "github-cli-attestation",
        "bundle_sha256": "a" * 64,
        "attestation_subject_digest": "sha256:" + "a" * 64,
        "repository": "org/repo",
        "source_sha": "b" * 40,
        "source_ref": "refs/heads/main",
        "signer_workflow": "org/repo/.github/workflows/path3-runtime-verification.yml",
        "verification_run_id": "1-1",
    }
    assert m.validate(o, expected_bundle_sha="a" * 64, expected_source_sha="b" * 40) == []
    assert "bundle_digest_mismatch" in m.validate(o, expected_bundle_sha="c" * 64)


def test_attested_image_manifest_rejects_tag_only_reference(tmp_path):
    m = load("scripts/ci/prepare_attested_runtime_images.py", "image_manifest_test")
    # structural guarantee is intentionally tested from the strict regex because main is CLI-bound.
    assert not m.REF.fullmatch("ghcr.io/org/image:latest")
    assert m.REF.fullmatch("ghcr.io/org/image@sha256:" + "a" * 64)


def test_attested_image_manifest_requires_complete_supply_chain_evidence():
    m = load("scripts/ci/prepare_attested_runtime_images.py", "image_evidence_test")
    evidence = {key: "a" * 64 for key in m.EVIDENCE_DIGESTS}
    assert m.valid_evidence_digests(evidence)
    missing = dict(evidence)
    missing.pop("sbom_verification_sha256")
    assert not m.valid_evidence_digests(missing)
    malformed = dict(evidence, vulnerability_scan_sha256="not-a-digest")
    assert not m.valid_evidence_digests(malformed)


def test_trusted_environment_binds_runner_builder_and_signer():
    o = json.loads((ROOT / "runtime-verification/trusted_environments.json").read_text())
    e = next(x for x in o["environments"] if x["environment_id"] == "staging-pg16")
    assert e["github_environment"] == "staging-pg16"
    assert "sahool-path3-trusted" in e["required_runner_labels"]
    assert e["require_pull_by_digest"] is True
    assert e["require_external_provenance_receipt"] is True


def test_bridge_receipt_validation_binds_actual_bundle(tmp_path):
    m = load("scripts/ci/runtime_identity_bridge.py", "bridge_receipt_test")
    bundle = tmp_path / "bundle.tgz"
    bundle.write_bytes(b"actual-bundle")
    import hashlib

    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    receipt = {
        "schema_version": "1.0",
        "verification_result": "verified",
        "verifier": "github-cli-attestation",
        "bundle_sha256": digest,
        "attestation_subject_digest": "sha256:" + digest,
        "repository": "org/repo",
        "source_sha": "a" * 40,
        "source_ref": "refs/heads/main",
        "signer_workflow": "org/repo/.github/workflows/path3-runtime-verification.yml",
        "verification_run_id": "1-1",
    }
    rp = tmp_path / "receipt.json"
    rp.write_text(json.dumps(receipt))
    evidence = {"soil-service": [{"environment_id": "staging-pg16"}]}
    assert m._validate_external_provenance(str(rp), "a" * 40, str(bundle), evidence) == []
    bundle.write_bytes(b"tampered")
    assert "bundle_digest_mismatch" in m._validate_external_provenance(
        str(rp), "a" * 40, str(bundle), evidence
    )
