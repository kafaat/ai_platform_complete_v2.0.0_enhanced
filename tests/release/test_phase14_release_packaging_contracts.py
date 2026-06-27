from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
