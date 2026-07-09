"""Guard: tests_v9 third-party imports must be declared in test requirements.

The unit CI job installs tests_v9/requirements-test.txt before collecting tests_v9.
This test delegates to the same static contract used by CI so missing packages are caught
before collection-time ModuleNotFoundError failures fan out across unrelated tests.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def test_unit_test_dependency_contract_is_current_and_exact_pinned():
    result = subprocess.run(
        [sys.executable, "scripts/ci/test_requirements_inventory_guard.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
