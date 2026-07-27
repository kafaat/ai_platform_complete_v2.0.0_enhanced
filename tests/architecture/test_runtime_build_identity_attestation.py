from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def test_identity_reader_ignores_mutable_environment(tmp_path, monkeypatch):
    m = load_module(ROOT / "shared/runtime_identity.py", "runtime_identity_test")
    p = tmp_path / "meta.json"
    p.write_text(
        json.dumps(
            {
                "service": "weather-service",
                "git_sha": "a" * 40,
                "build_id": "build-1",
                "source_repository": "org/repo",
                "source_ref": "refs/heads/main",
            }
        )
    )
    monkeypatch.setenv("SAHOOL_GIT_SHA", "b" * 40)
    monkeypatch.setenv("SAHOOL_BUILD_ID", "spoofed")
    got = m.load_build_identity("weather-service", p)
    assert got["git_sha"] == "a" * 40 and got["build_id"] == "build-1"
    assert got["metadata_source"] == "immutable-image-file"


def test_identity_reader_rejects_bad_metadata(tmp_path):
    m = load_module(ROOT / "shared/runtime_identity.py", "runtime_identity_bad_test")
    p = tmp_path / "meta.json"
    p.write_text(json.dumps({"service": "weather-service", "git_sha": "bad", "build_id": "x"}))
    with pytest.raises(m.BuildIdentityError):
        m.load_build_identity("weather-service", p)


def test_service_endpoints_do_not_read_identity_from_environment():
    # sahool-platform deliberately does NOT expose an HTTP /runtime-identity endpoint
    # (dropped to preserve the platform route-budget ratchet); its build identity comes
    # from the authoritative deployment manifest. Only the services that expose the
    # endpoint are asserted here.
    for rel in [
        "services/weather-service/main.py",
        "services/soil-service/main.py",
    ]:
        text = (ROOT / rel).read_text()
        block = text[text.index('@app.get("/runtime-identity"') :]
        block = block[: block.find("\n\n", 1)]
        assert "os.getenv" not in block
        assert "load_build_identity" in block


def test_dockerfiles_embed_immutable_metadata_and_oci_labels():
    for rel in [
        "services/weather-service/Dockerfile",
        "services/soil-service/Dockerfile",
        "services/sahool-platform/Dockerfile",
    ]:
        text = (ROOT / rel).read_text()
        assert "ARG SAHOOL_GIT_SHA" in text
        assert "org.opencontainers.image.revision" in text
        assert "/app/.sahool-build-metadata.json" in text
        assert "chmod 0444" in text


def test_compose_requires_build_identity_args():
    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text())
    for name in ["sahool-weather-service", "sahool-soil-service", "sahool-platform"]:
        args = compose["services"][name]["build"]["args"]
        assert "TESTED_SHA required" in args["SAHOOL_GIT_SHA"]
        assert "SAHOOL_BUILD_ID required" in args["SAHOOL_BUILD_ID"]


def test_path3_produces_transports_and_verifies_oidc_provenance():
    text = (ROOT / ".github/workflows/path3-runtime-verification.yml").read_text()
    assert (
        "functional-runtime-verifier"
        in (ROOT / "scripts/ci/path3_runtime_activation.py").read_text()
    )
    assert (
        "functional_probe_runner.py"
        in (ROOT / "docker-compose.runtime-verification.yml").read_text()
    )
    assert "actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6" in text
    assert "gh attestation verify" in text
    assert "--signer-workflow" in text and "--source-digest" in text and "--source-ref" in text
    assert "verify-and-evaluate:" in text


def test_image_digest_and_run_formats_are_strict():
    text = (ROOT / "scripts/ci/runtime_identity_bridge.py").read_text()
    assert "^sha256:[0-9a-f]{64}$" in text
    assert "invalid_build_id" in text and "invalid_run_id" in text


def test_path3_uses_external_attested_images_and_protected_boundaries():
    text = (ROOT / ".github/workflows/path3-runtime-verification.yml").read_text()
    assert "image_build_run_id" in text
    assert (
        "runtime-image-provenance.yml"
        in (ROOT / ".github/workflows/runtime-image-provenance.yml").read_text()
    )
    assert "runs-on: [self-hosted, linux, docker, sahool-path3-trusted]" in text
    assert "environment: staging-pg16" in text
    producer = text.split("runtime-producer:", 1)[1].split("trusted-signer:", 1)[0]
    assert "id-token: write" not in producer and "attestations: write" not in producer
    signer = text.split("trusted-signer:", 1)[1].split("verify-and-evaluate:", 1)[0]
    assert "runs-on: ubuntu-24.04" in signer
    assert "Attest evidence bundle in trusted signer boundary" in signer
    assert (
        "docker compose -f docker-compose.v9.yml -f verified-images/docker-compose.attested-images.yml pull"
        in text
    )
    assert 'gh attestation verify "oci://${image}"' in text


def test_bridge_requires_external_provenance_receipt_and_replay_guard():
    bridge = (ROOT / "scripts/ci/runtime_identity_bridge.py").read_text()
    workflow = (ROOT / ".github/workflows/path3-runtime-verification.yml").read_text()
    assert "external_provenance_receipt_required" in bridge
    assert "--provenance-receipt" in bridge
    assert "runtime_replay_guard.py" in workflow
    assert "path3-consumed-${{ env.BUNDLE_SHA256 }}" in workflow


def test_deployment_manifest_prefers_attested_registry_digest():
    text = (ROOT / "scripts/ci/runtime_deployment_manifest.py").read_text()
    assert "RepoDigests" in text
    assert "running image does not match attested pull-by-digest reference" in text
    assert '"docker_config_digest": image_id' in text
