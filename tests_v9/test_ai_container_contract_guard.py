from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_ai_container_contract_guard_passes():
    result = subprocess.run(
        [sys.executable, "scripts/ci/ai_container_contract_guard.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ai_container_contract_guard_ok" in result.stdout
