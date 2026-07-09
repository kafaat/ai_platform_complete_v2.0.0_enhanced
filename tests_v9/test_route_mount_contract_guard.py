from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_route_mount_contract_guard_passes():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "scripts/ci/route_mount_contract_guard.py", "--check"],
        cwd=root,
        check=True,
    )
