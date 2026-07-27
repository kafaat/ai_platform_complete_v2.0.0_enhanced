from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/static_governance_closure.py"


def load_module():
    spec = importlib.util.spec_from_file_location("static_governance_closure", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_closure_scope_never_claims_runtime_or_production():
    module = load_module()
    payload = module.closure_payload([], {"passed": True}, {})
    assert payload["runtime_verified"] is False
    assert payload["production_certified"] is False


def test_closure_requires_every_check_and_test_to_pass():
    module = load_module()
    closed = module.closure_payload([{"passed": True}], {"passed": True}, {})
    open_check = module.closure_payload([{"passed": False}], {"passed": True}, {})
    open_test = module.closure_payload([{"passed": True}], {"passed": False}, {})
    assert closed["status"] == "CLOSED"
    assert open_check["status"] == "OPEN"
    assert open_test["status"] == "OPEN"


def test_manifest_is_sorted_and_excludes_closure_self_hashes():
    module = load_module()
    paths = [p.relative_to(ROOT).as_posix() for p in module.artifact_files()]
    assert paths == sorted(paths)
    assert all(not path.startswith("governance/generated/") for path in paths)


def test_tracked_files_uses_signed_manifest_when_git_is_unavailable(tmp_path, monkeypatch):
    module = load_module()
    release = tmp_path / "release"
    release.mkdir()
    (release / "FILE_CHECKSUMS.sha256").write_text(
        "a" * 64
        + "  capabilities/generated/a.json\n"
        + "b" * 64
        + "  architecture/generated/b.json\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)

    def no_git(*args, **kwargs):
        raise module.subprocess.CalledProcessError(128, args[0])

    monkeypatch.setattr(module.subprocess, "run", no_git)
    assert module._tracked_files() == {
        "capabilities/generated/a.json",
        "architecture/generated/b.json",
    }


def test_tracked_files_fails_closed_without_git_or_signed_manifest(tmp_path, monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "ROOT", tmp_path)

    def no_git(*args, **kwargs):
        raise module.subprocess.CalledProcessError(128, args[0])

    monkeypatch.setattr(module.subprocess, "run", no_git)
    try:
        module._tracked_files()
    except RuntimeError as exc:
        assert "refusing to scan the raw filesystem" in str(exc)
    else:
        raise AssertionError("expected fail-closed RuntimeError")


def test_manifest_parser_rejects_unsafe_paths(tmp_path, monkeypatch):
    module = load_module()
    release = tmp_path / "release"
    release.mkdir()
    (release / "FILE_CHECKSUMS.sha256").write_text(
        "a" * 64 + "  ../escape.json\n", encoding="utf-8"
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)
    try:
        module._manifest_entries()
    except RuntimeError as exc:
        assert "unsafe path" in str(exc)
    else:
        raise AssertionError("expected unsafe manifest path to fail closed")


def test_manifest_file_checksum_is_verified(tmp_path, monkeypatch):
    module = load_module()
    release = tmp_path / "release"
    release.mkdir()
    artifact = tmp_path / "capabilities/generated/a.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}\n", encoding="utf-8")
    (release / "FILE_CHECKSUMS.sha256").write_text(
        "0" * 64 + "  capabilities/generated/a.json\n", encoding="utf-8"
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)
    try:
        module._verify_manifest_file("capabilities/generated/a.json", "0" * 64)
    except RuntimeError as exc:
        assert "checksum mismatch" in str(exc)
    else:
        raise AssertionError("expected checksum mismatch to fail closed")


def test_manifest_verification_is_not_bypassed_by_stale_git_marker(tmp_path, monkeypatch):
    module = load_module()
    (tmp_path / ".git").mkdir()
    release = tmp_path / "release"
    release.mkdir()
    artifact = tmp_path / "capabilities/generated/a.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}\n", encoding="utf-8")
    (release / "FILE_CHECKSUMS.sha256").write_text(
        "0" * 64 + "  capabilities/generated/a.json\n", encoding="utf-8"
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "ARTIFACT_ROOTS", [artifact.parent])

    def no_git(*args, **kwargs):
        raise module.subprocess.CalledProcessError(128, args[0])

    monkeypatch.setattr(module.subprocess, "run", no_git)
    try:
        module.artifact_files()
    except RuntimeError as exc:
        assert "checksum mismatch" in str(exc)
    else:
        raise AssertionError("stale .git marker bypassed manifest verification")


def test_git_parent_worktree_is_not_accepted_as_repository_root(tmp_path, monkeypatch):
    module = load_module()
    release = tmp_path / "release"
    release.mkdir()
    (release / "FILE_CHECKSUMS.sha256").write_text(
        "a" * 64 + "  capabilities/generated/a.json\n", encoding="utf-8"
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)

    calls = iter([str(tmp_path.parent) + "\n"])

    def parent_git(*args, **kwargs):
        command = args[0]
        if command[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return module.subprocess.CompletedProcess(command, 0, next(calls), "")
        raise AssertionError("git ls-files must not run for a mismatched worktree root")

    monkeypatch.setattr(module.subprocess, "run", parent_git)
    tracked, manifest = module._tracked_inventory()
    assert tracked == {"capabilities/generated/a.json"}
    assert manifest is not None
