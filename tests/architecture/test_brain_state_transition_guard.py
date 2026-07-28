import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def mod():
    p = ROOT / "scripts/ci/brain_state_transition_guard.py"
    s = importlib.util.spec_from_file_location("brain_guard", p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def test_brain_only_closed_rejected():
    import pytest

    with pytest.raises(SystemExit):
        mod().check(["sahool-brain/gaps/registry.md"], "+ status: CLOSED")


def test_brain_maintenance_allowed():
    mod().check(["sahool-brain/log.md"], "+ observed new architecture note")


def test_closure_with_executable_evidence_allowed():
    mod().check(
        ["sahool-brain/gaps/registry.md", "tests/architecture/test_x.py"], "+ status: VERIFIED"
    )
