from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "guard_mutation_guard_delta", ROOT / "scripts/ci/guard_mutation_guard.py"
)
gmg = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(gmg)

_GUARD_SRC = """\
def check(values):
    return [v for v in values if v < 0]
"""
_TEST_SRC = """\
def test_negative_is_rejected():
    assert True
"""


def _repo(tmp_path: Path):
    ci = tmp_path / "scripts" / "ci"
    ci.mkdir(parents=True)
    (ci / "fake_guard.py").write_text(_GUARD_SRC, encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_fake.py").write_text(_TEST_SRC, encoding="utf-8")
    return ci


def _base():
    return {
        "mutated": {},
        "behavioural": {},
        "unmutated_debt": {},
        "unmutated_debt_ceiling": 0,
    }


def test_a_mutation_shaped_top_level_entry_is_blocked(tmp_path: Path) -> None:
    ci = _repo(tmp_path)
    reg = _base()
    reg["scripts/architecture/stranded_guard.py"] = {
        "test": "tests/test_fake.py",
        "mutations": [
            {
                "why": "stranded",
                "find": "v < 0",
                "replace": "v < -99",
                "expect": "test_negative_is_rejected",
            }
        ],
    }
    failures = gmg.check(reg, ci, tmp_path)
    assert any("خارج القسمين القانونيّين" in f for f in failures)


def test_an_explicit_root_relative_guard_spec_is_plantable(tmp_path: Path) -> None:
    ci = _repo(tmp_path)
    arch = tmp_path / "scripts" / "architecture"
    arch.mkdir(parents=True)
    source = arch / "external_guard.py"
    source.write_text(_GUARD_SRC, encoding="utf-8")
    reg = _base()
    reg["unmutated_debt"] = {"fake_guard.py": "synthetic debt"}
    reg["unmutated_debt_ceiling"] = 1
    reg["mutated"] = {
        "scripts/architecture/external_guard.py": {
            "test": "tests/test_fake.py",
            "mutations": [
                {
                    "why": "external guard",
                    "find": "v < 0",
                    "replace": "v < -99",
                    "expect": "test_negative_is_rejected",
                }
            ],
        }
    }
    assert gmg.check(reg, ci, tmp_path) == []
    assert (
        gmg._mutated_source("scripts/architecture/external_guard.py", ci=ci, root=tmp_path)
        == source
    )
