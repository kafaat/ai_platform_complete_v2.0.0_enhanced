from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_contract_capabilities_schema_guard_is_clean() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/ci/contract_capabilities_schema_guard.py", "--check"],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
