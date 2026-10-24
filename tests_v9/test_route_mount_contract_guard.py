from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_help_exits_without_collecting_or_writing(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "route_mount_help_contract", root / "scripts/ci/route_mount_contract_guard.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def forbidden(*args, **kwargs):
        pytest.fail("--help must not inspect or mutate source inventories")

    monkeypatch.setattr(module, "collect", forbidden)
    monkeypatch.setattr(module, "write", forbidden)
    with pytest.raises(SystemExit) as error:
        module.main(["--help"])
    assert error.value.code == 0


def test_route_mount_contract_guard_passes():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "scripts/ci/route_mount_contract_guard.py", "--check"],
        cwd=root,
        check=True,
    )
