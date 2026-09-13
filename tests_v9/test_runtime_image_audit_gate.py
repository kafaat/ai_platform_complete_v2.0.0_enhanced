"""Execute the real CI shell step with a deterministic audit CLI double."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def audit_step():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == "pip-audit (gating — each runtime image)":
                assert not step.get("continue-on-error", False)
                return step["run"]
    raise AssertionError("blocking runtime-image audit is missing")


def run_audit(tmp_path, failure):
    files = [
        "services/raster-tiler-service/requirements.txt",
        "agents/notification/requirements.txt",
        "bots/telegram/requirements.txt",
    ]
    for name in files:
        target = tmp_path / name
        target.parent.mkdir(parents=True)
        target.write_text("synthetic-package==1.0\n", encoding="utf-8")
    binary = tmp_path / "bin"
    binary.mkdir()
    executable = binary / "pip-audit"
    executable.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$2" >> "$SAHOOL_TEST_AUDIT_LOG"\nexit "$SAHOOL_TEST_AUDIT_EXIT"\n',
        encoding="utf-8",
    )
    executable.chmod(0o755)
    logfile = tmp_path / "audited.txt"
    env = dict(
        os.environ,
        PATH=str(binary) + os.pathsep + os.environ["PATH"],
        SAHOOL_TEST_AUDIT_LOG=str(logfile),
        SAHOOL_TEST_AUDIT_EXIT=str(failure),
    )
    result = subprocess.run(
        ["bash", "-c", audit_step()],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    return result, logfile.read_text(encoding="utf-8").splitlines(), files


def test_clean_runtime_images_all_pass_the_actual_ci_step(tmp_path):
    result, visited, expected = run_audit(tmp_path, 0)
    assert result.returncode == 0, result.stderr
    assert sorted(visited) == sorted(expected)


def test_vulnerable_runtime_image_fails_the_actual_ci_step(tmp_path):
    result, visited, _ = run_audit(tmp_path, 1)
    assert result.returncode == 1
    assert len(visited) == 1
