from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def test_vegetation_container_contract_guard_passes():
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/vegetation_container_contract_guard.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "vegetation_container_contract_guard_ok" in res.stdout


def _guard():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_vegetation_container_contract_guard",
        ROOT / "scripts/ci/vegetation_container_contract_guard.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_service_module_imported_in_the_image_is_copied_into_it():
    guard = _guard()
    assert guard.missing_local_imports(guard._text(guard.DOCKERFILE)) == {}


def test_dropping_the_weekly_insights_copy_is_caught():
    """Regression #1228: the insights router imported a module the image never had."""
    guard = _guard()
    dockerfile = guard._text(guard.DOCKERFILE)
    line = "COPY services/vegetation-analysis-service/weekly_insights.py /app/weekly_insights.py\n"
    assert line in dockerfile
    missing = guard.missing_local_imports(dockerfile.replace(line, ""))
    assert missing == {"weekly_insights": ["routers/insights.py"]}


def test_dropping_a_module_imported_only_inside_a_function_is_caught():
    """anomaly_store_pg loads only when VEGETATION_ANOMALY_STORE=postgres; booting misses it."""
    guard = _guard()
    dockerfile = guard._text(guard.DOCKERFILE)
    line = (
        "COPY services/vegetation-analysis-service/anomaly_store_pg.py /app/anomaly_store_pg.py\n"
    )
    assert line in dockerfile
    missing = guard.missing_local_imports(dockerfile.replace(line, ""))
    assert missing == {"anomaly_store_pg": ["anomaly_runtime.py"]}
