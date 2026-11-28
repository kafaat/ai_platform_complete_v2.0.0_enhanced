from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_contract_capabilities_schema_guard_is_clean() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/ci/contract_capabilities_schema_guard.py", "--check"],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def contract_cli(tmp_path, monkeypatch):
    script = (
        Path(__file__).resolve().parents[1] / "scripts/ci/contract_capabilities_schema_guard.py"
    )
    spec = importlib.util.spec_from_file_location("contract_cli_fixture", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    service = tmp_path / "services/fixture/main.py"
    service.parent.mkdir(parents=True)
    service.write_text(
        '@app.get("/contract")\n'
        "def contract():\n"
        '    return {"service": "fixture", "contract_version": "1", "implemented_runtime": False}\n'
        '@app.get("/capabilities")\n'
        "def capabilities():\n"
        '    return {"service": "fixture", "schema_version": "1", "capabilities": []}\n',
        encoding="utf-8",
    )
    outputs = [
        tmp_path / "contract_capabilities_inventory.generated.json",
        tmp_path / "contract_capabilities_inventory.csv",
    ]
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "INVENTORY_JSON", outputs[0])
    monkeypatch.setattr(mod, "INVENTORY_CSV", outputs[1])
    build, calls = mod.build_inventory, []

    def counted_build():
        calls.append("build")
        return build()

    monkeypatch.setattr(mod, "build_inventory", counted_build)

    def invoke(arguments):
        try:
            return mod.main(arguments)
        except SystemExit as exc:
            return exc.code

    return mod, outputs, service, calls, invoke


@pytest.mark.parametrize("present", [False, True], ids=["missing", "stale"])
@pytest.mark.parametrize(
    ("arguments", "expected"),
    [(["--help"], 0), (["-h"], 0), (["--chec"], 2), (["--check", "--generate"], 2)],
    ids=["help", "short-help", "unknown-prefix", "conflicting-mode"],
)
def test_contract_cli_information_and_invalid_args_do_not_scan_or_write(
    contract_cli, present, arguments, expected, capsys
):
    _mod, outputs, _service, calls, invoke = contract_cli
    before = b"[]\n" if present else None
    if present:
        for output in outputs:
            output.write_bytes(before)
    result = invoke(arguments)
    assert [output.read_bytes() if output.exists() else None for output in outputs] == [before] * 2
    assert calls == [], "argument admission must precede the source scan"
    assert result == expected
    captured = capsys.readouterr()
    assert "usage:" in (captured.out if expected == 0 else captured.err)


def test_contract_cli_bare_generation_and_readonly_failure_are_preserved(contract_cli):
    mod, outputs, service, _calls, invoke = contract_cli
    assert invoke([]) == 0
    records = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert {row["endpoint"] for row in records} == {"/contract", "/capabilities"}
    assert all(row["status"] == "ok" for row in records)
    assert invoke(["--check"]) == 0
    before = [path.read_bytes() for path in outputs]
    service.write_text('@app.get("/contract")\ndef contract():\n    return {}\n', encoding="utf-8")
    assert invoke(["--check"]) == 1
    assert [path.read_bytes() for path in outputs] == before
    # Explicit bare generation still records the measured invalid schema and fails.
    assert invoke([]) == 1
    assert json.loads(outputs[0].read_text(encoding="utf-8"))[0]["status"] == "missing_keys"
    outputs[0].unlink()
    assert invoke(["--check"]) == 1
    assert not outputs[0].exists()
