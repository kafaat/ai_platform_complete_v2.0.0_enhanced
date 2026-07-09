from pathlib import Path
import subprocess


def test_platform_main_subinventory_guard_passes():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["python", "scripts/ci/platform_main_subinventory_guard.py", "--check"],
        cwd=root,
        check=True,
    )
