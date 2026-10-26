from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_p2_main_decomposition_guard() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/ci/p2_main_decomposition_guard.py")],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "p2_main_decomposition_guard_ok" in result.stdout


def _guard():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts/ci/p2_main_decomposition_guard.py"
    spec = importlib.util.spec_from_file_location("p2_main_decomposition_guard_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "source",
    [
        "import actuator_runtime\n",
        "import actuator_runtime as _runtime\n",
        "from actuator_runtime import *\n",
        "from actuator_runtime import app, register_routers\n",
    ],
)
def test_a_real_import_counts(source: str) -> None:
    assert _guard()._imports_module(source, "actuator_runtime") is True


@pytest.mark.parametrize(
    "source",
    [
        # The case that hid the weakness: the docstring names the import, the code does not.
        '"""Unlike ``from actuator_runtime import *``, this shell re-exports."""\n',
        "# from actuator_runtime import *\n",
        "import actuator_runtime_v2\n",
        "from .actuator_runtime import app\n",
    ],
)
def test_text_that_only_mentions_the_module_does_not_count(source: str) -> None:
    assert _guard()._imports_module(source, "actuator_runtime") is False
