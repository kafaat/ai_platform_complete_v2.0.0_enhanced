from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_fii_runtime_role_static_gate():
    result = subprocess.run(
        [sys.executable, "scripts/security/fii_rls_role_gate.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
