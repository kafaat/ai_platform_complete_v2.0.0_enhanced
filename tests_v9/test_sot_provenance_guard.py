from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/ci/sot_provenance_guard.py"
spec = importlib.util.spec_from_file_location("sot_provenance_guard", PATH)
assert spec is not None and spec.loader is not None
MOD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MOD)


def _policy():
    return {
        "repository": "kafaat/ai_platform_complete_v2.0.0_enhanced",
        "signer_workflow": "kafaat/ai_platform_complete_v2.0.0_enhanced/.github/workflows/ci.yml",
        "predicate_type": "https://slsa.dev/provenance/v1",
        "oidc_issuer": "https://token.actions.githubusercontent.com",
        "gh_cli": {"version": "2.93.0"},
    }


def test_gh_command_requires_exact_signer_workflow_and_oidc(tmp_path):
    cmd = MOD.build_gh_command(
        gh="gh",
        subject=tmp_path / "a",
        bundle=tmp_path / "b",
        trusted_root=tmp_path / "r",
        policy=_policy(),
        tested_commit="a" * 40,
        source_ref="refs/pull/829/merge",
    )
    assert cmd[cmd.index("--signer-workflow") + 1] == _policy()["signer_workflow"]
    assert cmd[cmd.index("--cert-oidc-issuer") + 1] == _policy()["oidc_issuer"]


def test_gh_command_requires_source_digest_and_ref(tmp_path):
    cmd = MOD.build_gh_command(
        gh="gh",
        subject=tmp_path / "a",
        bundle=tmp_path / "b",
        trusted_root=tmp_path / "r",
        policy=_policy(),
        tested_commit="b" * 40,
        source_ref="refs/pull/829/merge",
    )
    assert cmd[cmd.index("--source-digest") + 1] == "b" * 40
    assert cmd[cmd.index("--source-ref") + 1] == "refs/pull/829/merge"


def test_gh_command_denies_self_hosted_and_uses_trusted_root(tmp_path):
    root = tmp_path / "trusted.jsonl"
    cmd = MOD.build_gh_command(
        gh="gh",
        subject=tmp_path / "a",
        bundle=tmp_path / "b",
        trusted_root=root,
        policy=_policy(),
        tested_commit="c" * 40,
        source_ref="refs/heads/main",
    )
    assert "--deny-self-hosted-runners" in cmd
    assert cmd[cmd.index("--custom-trusted-root") + 1] == str(root)


def _manifest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = pathlib.Path("subject.json")
    p.write_text("{}", encoding="utf-8")
    m = {
        "schema": "sahool.evidence-manifest/v1",
        "closure": {"mode": "exact", "transport_exclusions": ["transport.json"]},
        "files": [
            {"path": "subject.json", "sha256": MOD.sha256(p), "size_bytes": p.stat().st_size}
        ],
    }
    mp = pathlib.Path("manifest.json")
    mp.write_bytes(MOD.canonical_manifest_bytes(m))
    return p, mp, m


def test_digest_mismatch_is_rejected(tmp_path, monkeypatch):
    p, mp, m = _manifest(tmp_path, monkeypatch)
    m["files"][0]["sha256"] = "0" * 64
    mp.write_bytes(MOD.canonical_manifest_bytes(m))
    with pytest.raises(RuntimeError, match="SUBJECT_DIGEST_MISMATCH"):
        MOD.validate_manifest(mp, m, [p, mp, pathlib.Path("transport.json")])


def test_unmanifested_file_is_rejected_by_exact_closure(tmp_path, monkeypatch):
    p, mp, m = _manifest(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="MANIFEST_CLOSURE_MISMATCH"):
        MOD.validate_manifest(
            mp, m, [p, mp, pathlib.Path("transport.json"), pathlib.Path("evil.bin")]
        )


def test_missing_manifested_file_is_rejected(tmp_path, monkeypatch):
    p, mp, m = _manifest(tmp_path, monkeypatch)
    p.unlink()
    with pytest.raises(RuntimeError, match="MANIFEST_MISSING"):
        MOD.validate_manifest(mp, m, [p, mp, pathlib.Path("transport.json")])


def test_failed_gh_verification_never_becomes_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", "bad")
    )
    with pytest.raises(RuntimeError, match="ATTESTATION_CRYPTO_INVALID"):
        MOD.verify_subject(
            tmp_path / "s",
            gh="gh",
            bundle=tmp_path / "b",
            trusted_root=tmp_path / "r",
            policy=_policy(),
            tested_commit="d" * 40,
            source_ref="refs/heads/main",
        )


def test_pending_pr_binding_cannot_reach_release_bound():
    assert (
        MOD.release_bound(
            {
                "tested_identity": {"commit_sha": "a" * 40, "tree_sha": "b" * 40},
                "release_binding": {"mode": "pending_final_rerun"},
            }
        )
        is False
    )


def test_exact_commit_binding_requires_same_commit():
    m = {
        "tested_identity": {"commit_sha": "a" * 40, "tree_sha": "b" * 40},
        "release_binding": {"mode": "exact_commit", "accepted_commit_sha": "c" * 40},
    }
    assert MOD.release_bound(m) is False
