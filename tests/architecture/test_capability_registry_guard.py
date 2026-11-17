from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_capability_registry_guard_is_clean() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/ci/capability_registry_guard.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_capability_ids_are_unique() -> None:
    data = json.loads(
        (ROOT / "capabilities/registry/capabilities.json").read_text(encoding="utf-8")
    )
    ids = [c["id"] for c in data["capabilities"]]
    assert len(ids) == len(set(ids))


def test_no_capability_is_production_certified_without_runtime_evidence() -> None:
    data = json.loads(
        (ROOT / "capabilities/registry/capabilities.json").read_text(encoding="utf-8")
    )
    for c in data["capabilities"]:
        if c["production_certified"]:
            assert c["maturity"] == 5 and c["evidence_level"] == 5
            assert all(c["runtime"][k] for k in ("metrics", "traces", "receipts", "audit_events"))


def _load_guard():
    """The guard as a module, so its outputs can be pointed at a scratch directory."""
    import importlib.util

    ci = str(ROOT / "scripts/ci")
    if ci not in sys.path:
        sys.path.insert(0, ci)
    spec = importlib.util.spec_from_file_location(
        "capability_registry_guard_under_test", ROOT / "scripts/ci/capability_registry_guard.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scratch_outputs(module, tmp_path: Path) -> list:
    module.GENERATED = tmp_path / "capabilities/generated"
    arts = module.artifacts(module.load_registry())
    module.write_all(arts)
    return arts


def test_check_fails_naming_a_drifted_artifact(tmp_path, capsys) -> None:
    """``--check`` validated the registry and never read its own outputs.

    ``capability_summary.json`` kept saying 75 capabilities at maturity 3 while the
    authorities said 60, and every gate stayed green. Each output, corrupted on its own,
    must now fail the check and be named.
    """
    module = _load_guard()
    arts = _scratch_outputs(module, tmp_path)
    assert module.main(["--check"]) == 0
    for art in arts:
        good = art.path.read_bytes()
        art.path.write_bytes(good + b" ")
        capsys.readouterr()
        assert module.main(["--check"]) == 1, f"drift in {art.path.name} passed the check"
        assert art.path.name in capsys.readouterr().err
        art.path.write_bytes(good)
    arts[0].path.unlink()
    assert module.main(["--check"]) == 1


def test_check_reads_and_never_writes(tmp_path) -> None:
    """A check that repairs what it checks measures itself, not the tree."""
    module = _load_guard()
    arts = _scratch_outputs(module, tmp_path)
    stale = arts[0].path
    stale.write_bytes(b"{}\n")
    assert module.main(["--check"]) == 1
    assert stale.read_bytes() == b"{}\n"


def test_generate_restores_byte_for_byte_and_is_idempotent(tmp_path) -> None:
    module = _load_guard()
    arts = _scratch_outputs(module, tmp_path)
    expected = {a.path: a.path.read_bytes() for a in arts}
    for path in expected:
        path.write_bytes(b"corrupt")
    assert module.main(["--generate"]) == 0
    assert {p: p.read_bytes() for p in expected} == expected
    assert module.main(["--generate"]) == 0
    assert {p: p.read_bytes() for p in expected} == expected
    assert module.main(["--check"]) == 0
