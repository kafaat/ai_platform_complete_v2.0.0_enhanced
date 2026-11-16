"""Run UWRP routing regressions in the repository's mandatory unit test job.

The self-contained Agent Skills test suite lives outside pytest.ini's testpaths.
Without this adapter, a pull request can modify work-router and still get green
unit CI without ever executing the updated phase-selection regression tests.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / ".claude" / "skills" / "work-router" / "tests" / "test_pack.py"


def test_work_router_full_pack_runs_in_unit_ci() -> None:
    assert SUITE.is_file(), "work-router regression suite is missing"
    result = subprocess.run(
        [sys.executable, str(SUITE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"work-router suite failed (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # unittest must really execute cases; an empty 0-exit script is not a pass.
    assert "Ran " in result.stderr and "OK" in result.stderr
