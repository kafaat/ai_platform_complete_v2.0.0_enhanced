from __future__ import annotations

import subprocess
import sys


def test_p1_main_decomposition_guard_passes():
    subprocess.run(
        [sys.executable, "scripts/ci/p1_main_decomposition_guard.py"],
        check=True,
    )
