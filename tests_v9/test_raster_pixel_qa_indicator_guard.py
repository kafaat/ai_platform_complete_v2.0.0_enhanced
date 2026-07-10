from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def test_raster_pixel_qa_indicator_guard_passes():
    subprocess.run(
        [sys.executable, "scripts/ci/raster_pixel_qa_indicator_guard.py"],
        cwd=ROOT,
        check=True,
    )
