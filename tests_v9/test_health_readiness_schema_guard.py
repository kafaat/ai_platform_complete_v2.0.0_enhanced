import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_health_readiness_schema_guard_clean():
    result = subprocess.run(
        [sys.executable, "scripts/ci/health_readiness_schema_guard.py", "--check"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "health_readiness_schema_guard_ok" in result.stdout
