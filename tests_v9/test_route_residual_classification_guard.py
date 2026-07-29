import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_route_residual_classification_guard_passes():
    subprocess.run(
        [sys.executable, "scripts/ci/route_residual_classification_guard.py", "--check"],
        check=True,
    )
