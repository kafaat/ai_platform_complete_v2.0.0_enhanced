import subprocess
import sys


def test_production_evidence_pack_guard_passes():
    subprocess.run(
        [sys.executable, "scripts/ci/production_evidence_pack_guard.py", "--check"],
        check=True,
    )
