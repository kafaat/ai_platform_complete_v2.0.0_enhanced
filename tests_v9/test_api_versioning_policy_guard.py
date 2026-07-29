from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_api_versioning_policy_guard_inventory_is_current():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "scripts/ci/api_versioning_policy_guard.py", "--check"],
        cwd=root,
        check=True,
    )
