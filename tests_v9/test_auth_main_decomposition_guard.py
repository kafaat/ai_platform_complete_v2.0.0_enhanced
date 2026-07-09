from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_auth_main_decomposition_guard():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "scripts/ci/auth_main_decomposition_guard.py"],
        cwd=root,
        check=True,
    )
