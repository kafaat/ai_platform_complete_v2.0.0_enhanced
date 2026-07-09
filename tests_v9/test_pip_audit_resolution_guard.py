from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def test_pip_audit_resolution_guard_passes():
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/pip_audit_resolution_guard.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "pip_audit_resolution_guard_ok" in res.stdout
