from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_internal_graphql_security_guard_passes():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "scripts/ci/internal_graphql_security_guard.py"],
        cwd=root,
        check=True,
    )
