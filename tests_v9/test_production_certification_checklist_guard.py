from pathlib import Path
import subprocess


def test_production_certification_checklist_guard_passes():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["python", "scripts/ci/production_certification_checklist_guard.py", "--check"],
        cwd=root,
        check=True,
    )
