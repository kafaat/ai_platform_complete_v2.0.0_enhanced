import subprocess
import sys


def test_route_residual_classification_guard_passes():
    subprocess.run(
        [sys.executable, "scripts/ci/route_residual_classification_guard.py", "--check"],
        check=True,
    )
