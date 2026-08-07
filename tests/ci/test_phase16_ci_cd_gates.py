from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ci_gate_assets_are_present_and_wired() -> None:
    result = subprocess.run(
        ["python3", "scripts/ci/validate_ci_gates.py", "--root", str(ROOT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_local_quality_gate_invokes_blocking_gates() -> None:
    script = (ROOT / "scripts/ci/local_quality_gate.sh").read_text(encoding="utf-8")
    required = [
        "scripts/production_validation_gate.sh",
        "scripts/security_audit.sh",
        "scripts/observability/validate_observability_assets.py",
        "scripts/deploy/validate_helm_readiness.py",
        "scripts/release/validate_release_package.py",
        "scripts/migrations/validate_migration_manifest.py",
        "pytest",
        "py_compile",
    ]
    for token in required:
        assert token in script


def test_production_workflow_has_no_soft_failures() -> None:
    workflow = (ROOT / ".github/workflows/sahool-production-gates.yml").read_text(encoding="utf-8")
    assert "continue-on-error: true" not in workflow, "بوّابةٌ لا تحجب تُقرأ حراسةً وهي تقرير"
    assert "pull_request_target" not in workflow, (
        "يشتغل بأسرار المستودع على شيفرة الفرع الوارد — تصعيد صلاحيّة"
    )
    assert "permissions:" in workflow
    assert "contents: read" in workflow


def test_release_builder_tracks_ci_assets() -> None:
    builder = (ROOT / "scripts/release/build_release_bundle.py").read_text(encoding="utf-8")
    for token in [
        "scripts/ci/validate_ci_gates.py",
        "scripts/ci/local_quality_gate.sh",
        ".github/workflows/sahool-production-gates.yml",
        "scripts/migrations/validate_migration_manifest.py",
    ]:
        assert token in builder


def test_workflow_shell_blocks_are_bash_syntax_checked() -> None:
    from scripts.ci.validate_ci_gates import validate_workflow_shell_blocks

    broken = """
name: Broken
jobs:
  scan:
    steps:
      - name: bad shell
        run: |
          if bad_event="pull_request""_target"
          if grep -R bad .github/workflows; then
            exit 1
          fi
"""
    errors = validate_workflow_shell_blocks(broken)
    assert errors, "broken GitHub Actions shell blocks must fail static CI validation"


def test_chaos_harness_does_not_hide_e2e_or_outbox_failures() -> None:
    script = (ROOT / "scripts/chaos/run_chaos_tests.sh").read_text(encoding="utf-8")
    assert "e2e_field_imagery_ai.sh || true" not in script
    assert "outbox_reliability_check.sh || true" not in script
    assert "bash scripts/recovery/recovery_smoke.sh" in script
