from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_raw_data_processing_contract_guard_passes():
    result = subprocess.run(
        [sys.executable, "scripts/ci/raw_data_processing_contract_guard.py"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "raw_data_processing_contract_ok" in result.stdout
