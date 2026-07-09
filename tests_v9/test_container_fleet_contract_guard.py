from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_container_fleet_contract_guard_passes():
    result = subprocess.run(
        [sys.executable, "scripts/ci/container_fleet_contract_guard.py"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "container_fleet_contract_guard_ok" in result.stdout
