from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_p2_main_decomposition_guard() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/ci/p2_main_decomposition_guard.py")],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "p2_main_decomposition_guard_ok" in result.stdout
