import subprocess
import sys


def test_report_index_guard_passes():
    subprocess.run([sys.executable, "scripts/ci/report_index_guard.py", "--check"], check=True)
