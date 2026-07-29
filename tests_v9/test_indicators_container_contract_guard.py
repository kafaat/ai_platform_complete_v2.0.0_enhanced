from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_indicators_container_contract_guard_passes():
    result = subprocess.run(
        [sys.executable, "scripts/ci/indicators_container_contract_guard.py"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "indicators_container_contract_guard_ok" in result.stdout
