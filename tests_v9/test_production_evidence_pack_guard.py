import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_production_evidence_pack_guard_passes():
    subprocess.run(
        [sys.executable, "scripts/ci/production_evidence_pack_guard.py", "--check"],
        check=True,
    )
