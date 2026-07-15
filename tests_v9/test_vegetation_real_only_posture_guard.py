"""Unit gate for the VEGETATION_REAL_ONLY fail-closed posture guard.

Runs in `pytest -m unit` (feature-branch CI) so the production fail-closed default
is enforced on every branch push, not only on main/develop.
"""

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "ci" / "vegetation_real_only_posture_guard.py"


def test_guard_passes_on_current_tree():
    result = subprocess.run(
        [sys.executable, str(GUARD)], capture_output=True, text=True, cwd=str(ROOT)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "vegetation_real_only_posture_guard_ok" in result.stdout


def test_production_compose_defaults_fail_closed():
    text = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
    assert "VEGETATION_REAL_ONLY: ${VEGETATION_REAL_ONLY:-1}" in text
    assert 'VEGETATION_REAL_ONLY: "0"' not in text


def test_dev_override_soft_fails_explicitly():
    text = (ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8")
    assert 'VEGETATION_REAL_ONLY: "0"' in text
