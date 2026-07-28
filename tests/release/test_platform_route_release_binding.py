from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.release import platform_route_release_binding as binding


def test_committed_source_binding_is_current() -> None:
    binding.check_source_binding()


def test_archive_binding_captures_exact_archive_and_governance(tmp_path: Path) -> None:
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("VERSION", "test\n")
    document = binding.build_archive_binding(archive)
    assert document["artifact"]["sha256"] == binding.sha256_file(archive)
    assert document["artifact"]["size_bytes"] == archive.stat().st_size
    assert (
        document["route_governance_statement_sha256"]
        == binding.build_source_binding()["route_governance_statement_sha256"]
    )


def test_archive_binding_rejects_artifact_mutation(tmp_path: Path) -> None:
    archive = tmp_path / "release.zip"
    archive.write_bytes(b"first")
    sidecar = tmp_path / "binding.json"
    sidecar.write_text(
        binding.canonical_json(binding.build_archive_binding(archive)), encoding="utf-8"
    )
    archive.write_bytes(b"second")
    with pytest.raises(AssertionError, match="does not match"):
        binding.check_archive_binding(archive, sidecar)


def test_source_binding_contains_current_route_counts() -> None:
    source = binding.build_source_binding()
    assert source["route_counts"] == {
        "raw_routes": 630,
        "infrastructure_routes": 4,
        "domain_budget_routes": 626,
        "domain_route_budget": 629,
        "full_ownership_surface": 634,
    }
    assert len(source["inputs"]) == 3
    assert all(len(item["sha256"]) == 64 for item in source["inputs"])


def test_source_binding_rejects_stale_content(tmp_path: Path) -> None:
    stale = tmp_path / "binding.json"
    stale.write_text(json.dumps({"schema_version": "stale"}) + "\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="stale"):
        binding.check_source_binding(stale)


def test_cli_check_mode_does_not_rewrite_tampered_sidecar(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "release.zip"
    archive.write_bytes(b"release")
    sidecar = tmp_path / "release.zip.route-governance.json"
    document = binding.build_archive_binding(archive)
    document["route_counts"]["domain_budget_routes"] -= 1
    tampered = binding.canonical_json(document)
    sidecar.write_text(tampered, encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "platform_route_release_binding.py",
            "--archive",
            str(archive),
            "--check-archive-binding",
            str(sidecar),
        ],
    )
    with pytest.raises(AssertionError, match="does not match"):
        binding.main()
    assert sidecar.read_text(encoding="utf-8") == tampered


def test_cli_write_then_independent_check(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "release.zip"
    archive.write_bytes(b"release")
    sidecar = tmp_path / "binding.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "platform_route_release_binding.py",
            "--archive",
            str(archive),
            "--output",
            str(sidecar),
        ],
    )
    assert binding.main() == 0
    before = sidecar.read_text(encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "platform_route_release_binding.py",
            "--archive",
            str(archive),
            "--check-archive-binding",
            str(sidecar),
        ],
    )
    assert binding.main() == 0
    assert sidecar.read_text(encoding="utf-8") == before
