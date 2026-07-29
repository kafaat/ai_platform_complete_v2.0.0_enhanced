from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_health_alias_contract_guard_passes():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "scripts/ci/health_alias_contract_guard.py"],
        cwd=root,
        check=True,
    )
