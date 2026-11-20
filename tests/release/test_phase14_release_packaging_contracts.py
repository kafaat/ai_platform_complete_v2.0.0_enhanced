from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.release.generate_dependency_sbom import collect

ROOT = Path(__file__).resolve().parents[2]


def test_release_assets_exist() -> None:
    required = [
        "VERSION",
        "RELEASE_NOTES_20260626.md",
        "PHASE14_RELEASE_PACKAGING_DEPLOYMENT_READINESS_REPORT_20260626.md",
        "release/DEPLOYMENT_READINESS_CHECKLIST.md",
        "release/SAHOOL_RELEASE_MANIFEST_20260626.json",
        "release/FILE_CHECKSUMS.sha256",
        "release/SBOM_MINIMAL.json",
        "scripts/release/build_release_bundle.py",
        "scripts/release/validate_release_package.py",
    ]
    missing = [item for item in required if not (ROOT / item).exists()]
    assert not missing


def test_release_manifest_has_no_missing_required_assets() -> None:
    manifest = json.loads((ROOT / "release/SAHOOL_RELEASE_MANIFEST_20260626.json").read_text())
    assert manifest["release_name"].startswith("SAHOOL_PHASE12_PRODUCTION_CANDIDATE")
    assert manifest["missing_required_assets"] == []
    assert manifest["file_count"] > 100
    assert "scripts/production_validation_gate.sh" in manifest["deployment_gates"]
    assert "scripts/release/validate_release_package.py" in manifest["deployment_gates"]


def test_release_checksum_validator_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/release/validate_release_package.py", "--root", str(ROOT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "checksums verified" in result.stdout


def test_deployment_checklist_contains_runtime_and_reliability_gates() -> None:
    checklist = (ROOT / "release/DEPLOYMENT_READINESS_CHECKLIST.md").read_text()
    for token in [
        "production_validation_gate.sh",
        "runtime_smoke.sh",
        "e2e_field_imagery_ai.sh",
        "run_load_tests.sh",
        "run_chaos_tests.sh",
        "recovery_smoke.sh",
    ]:
        assert token in checklist


def _sbom_declarations(component: dict[str, object]) -> list[dict[str, object]]:
    return [
        json.loads(prop["value"])
        for prop in component["properties"]
        if prop["name"] == "sahool:dependency-declaration"
    ]


def test_sbom_preserves_pinned_extras_and_line_provenance(tmp_path: Path) -> None:
    raw = "python-jose[cryptography]==3.5.0  # backend selected explicitly"
    (tmp_path / "requirements.txt").write_text(f"# dependencies\n{raw}\n", encoding="utf-8")
    components = collect(tmp_path)
    assert len(components) == 1
    component = components[0]
    assert component["name"] == "python-jose"
    assert component["version"] == "3.5.0"
    assert component["purl"] == "pkg:pypi/python-jose@3.5.0"
    assert _sbom_declarations(component) == [
        {
            "manifest": "requirements.txt",
            "line": 2,
            "raw": raw,
            "extras": ["cryptography"],
            "specifier": "==3.5.0",
            "marker": None,
            "url": None,
        }
    ]


@pytest.mark.parametrize(
    "requirement",
    [
        "example[extra]>=1.2,<2",
        "example~=1.2",
        "example==1.2.*",
        "example",
        "example==1.2,>=2",
    ],
)
def test_sbom_does_not_invent_python_versions(tmp_path: Path, requirement: str) -> None:
    (tmp_path / "requirements.txt").write_text(requirement + "\n", encoding="utf-8")
    components = collect(tmp_path)
    assert len(components) == 1
    component = components[0]
    assert component["name"] == "example"
    assert "version" not in component
    assert "purl" not in component
    assert {"name": "sahool:version-status", "value": "unresolved"} in component["properties"]
    assert _sbom_declarations(component)[0]["raw"] == requirement


@pytest.mark.parametrize(
    ("requirement", "version"),
    [
        ("example==1.2,>=1", "1.2"),
        ("example==1.2rc1,>=1.2rc1", "1.2rc1"),
        ("example===vendor-build", "vendor-build"),
    ],
)
def test_sbom_retains_satisfiable_declared_pins(
    tmp_path: Path, requirement: str, version: str
) -> None:
    (tmp_path / "requirements.txt").write_text(requirement + "\n", encoding="utf-8")
    component = collect(tmp_path)[0]
    assert component["version"] == version
    assert {"name": "sahool:version-status", "value": "declared-pin"} in component["properties"]


def test_sbom_keeps_conditional_markers_without_evaluating_them(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        'example==1.2; python_version < "2.0"\nexample[ssl]==1.2; sys_platform == "win32"\n',
        encoding="utf-8",
    )
    components = collect(tmp_path)
    assert len(components) == 1
    declarations = _sbom_declarations(components[0])
    assert {item["marker"] for item in declarations} == {
        'python_version < "2.0"',
        'sys_platform == "win32"',
    }
    assert any(item["extras"] == ["ssl"] for item in declarations)


def test_sbom_preserves_direct_reference_and_fragment_without_guessing_version(
    tmp_path: Path,
) -> None:
    url = "https://example.invalid/example-1.2.whl#sha256=1234"
    raw = f'example[ssl] @ {url} ; python_version < "2.0"'
    (tmp_path / "requirements.txt").write_text(raw + "\n", encoding="utf-8")
    component = collect(tmp_path)[0]
    assert "version" not in component
    assert "purl" not in component
    declaration = _sbom_declarations(component)[0]
    assert declaration["url"] == url
    assert declaration["raw"] == raw
    assert declaration["marker"] == 'python_version < "2.0"'


def test_sbom_deduplicates_components_but_keeps_every_declaration(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "Example_Pkg==1.2\nExample_Pkg==1.2\n", encoding="utf-8"
    )
    service = tmp_path / "service"
    service.mkdir()
    (service / "requirements.txt").write_text("example-pkg[extra]==1.2\n", encoding="utf-8")
    first = collect(tmp_path)
    assert first == collect(tmp_path)
    assert len(first) == 1
    assert first[0]["name"] == "example-pkg"
    assert first[0]["version"] == "1.2"
    assert len(_sbom_declarations(first[0])) == 3
    assert {
        prop["value"] for prop in first[0]["properties"] if prop["name"] == "sahool:source-manifest"
    } == {"requirements.txt", "service/requirements.txt"}


@pytest.mark.parametrize(
    "declaration",
    ["^1.2.3", "~1.2.3", ">=1.2.3", "1.x", "workspace:*", "file:../pkg", "latest"],
)
def test_sbom_does_not_invent_npm_versions(tmp_path: Path, declaration: str) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"example": declaration}}), encoding="utf-8"
    )
    component = collect(tmp_path)[0]
    assert "version" not in component
    assert "purl" not in component
    assert _sbom_declarations(component) == [
        {"manifest": "package.json", "section": "dependencies", "raw": declaration}
    ]


def test_sbom_retains_npm_pin_and_development_provenance(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"@scope/example": "1.2.3-beta.1+build"}}), encoding="utf-8"
    )
    component = collect(tmp_path)[0]
    assert component["version"] == "1.2.3-beta.1+build"
    assert component["purl"] == "pkg:npm/%40scope/example@1.2.3-beta.1%2Bbuild"
    assert _sbom_declarations(component)[0]["section"] == "devDependencies"


@pytest.mark.parametrize("raw", ["broken!requirement", "-r custom-pins.in"])
def test_sbom_rejects_unsupported_lines_instead_of_silently_omitting_them(
    tmp_path: Path, raw: str
) -> None:
    (tmp_path / "requirements.txt").write_text("# header\n" + raw + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"requirements\.txt:2"):
        collect(tmp_path)


def test_sbom_help_does_not_need_installed_packaging() -> None:
    result = subprocess.run(
        [sys.executable, "-S", str(ROOT / "scripts/release/generate_dependency_sbom.py"), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "--output" in result.stdout


def test_sbom_cli_declares_prebuild_scope_and_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(
        "python-jose[cryptography]>=3.4.0\n", encoding="utf-8"
    )
    output = tmp_path / "sbom.json"
    command = [
        sys.executable,
        str(ROOT / "scripts/release/generate_dependency_sbom.py"),
        "--root",
        str(tmp_path),
        "--output",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    first = output.read_bytes()
    payload = json.loads(first)
    assert payload["bomFormat"] == "CycloneDX"
    assert payload["specVersion"] == "1.6"
    assert payload["metadata"]["lifecycles"] == [{"phase": "pre-build"}]
    assert {"name": "sahool:dependency-resolution", "value": "not-performed"} in payload[
        "metadata"
    ]["properties"]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.read_bytes() == first
