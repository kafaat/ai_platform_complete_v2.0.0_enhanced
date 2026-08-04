"""The reachability guard must resolve the import forms this tree actually uses.

Two defects in the guard's first draft were caught by checking its output against a
module the record said was wired, rather than trusting the verdict:

* ``pkg/__init__.py`` was indexed only as ``pkg.__init__``, so every chain passing
  through a package looked broken and ten already-wired canonical modules were
  reported dead;
* relative imports (``from .canonical_water import …``) were never resolved.

A guard that under-resolves imports does not merely miss defects — it manufactures
them, which is worse than having no guard. These tests pin both resolutions and the
classification vocabulary.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts/ci/platform_module_reachability_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("_reach_guard", GUARD)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_a_package_answers_to_its_own_dotted_name():
    """`from core.crop_intelligence import x` must resolve to the package __init__."""
    guard = _load()
    files = guard.platform_modules()
    index = guard._dotted_index(files)
    assert "core.crop_intelligence" in index
    assert index["core.crop_intelligence"] == "core/crop_intelligence/__init__.py"


def test_relative_imports_resolve_against_the_importing_package():
    """api/field_state_projection.py reaches canonical_water by `from .canonical_water`."""
    guard = _load()
    files = guard.platform_modules()
    edges = guard.import_graph(files)
    assert "api/canonical_water.py" in edges["api/field_state_projection.py"]


def test_a_module_behind_a_package_is_reachable_not_terminal():
    """The concrete regression: canonical_inputs is reached through the package."""
    guard = _load()
    verdict = guard.classify()
    assert verdict["core/crop_intelligence/canonical_inputs.py"] != guard.TERMINAL


def test_the_persisted_chain_is_route_reachable():
    guard = _load()
    verdict = guard.classify()
    for module in (
        "api/agronomic_state_consumers.py",
        "api/persisted_canonical_repositories.py",
        "api/canonical_phenology_state.py",
        "api/canonical_salinity_state.py",
        "api/canonical_nutrient_ledger.py",
    ):
        assert verdict[module] == guard.MOUNTED_ROUTE, module


def test_a_module_nothing_executes_is_terminal():
    """Without a terminal verdict the classification cannot say anything is dead."""
    guard = _load()
    verdict = guard.classify()
    assert any(v == guard.TERMINAL for v in verdict.values()), (
        "a classification with no terminal verdict cannot distinguish live from dead code"
    )


def test_only_executable_roots_count_toward_the_baseline():
    guard = _load()
    assert guard.TERMINAL not in guard.COUNTABLE
    assert set(guard.COUNTABLE) == {
        guard.MOUNTED_ROUTE,
        guard.REGISTERED_WORKER,
        guard.EVENT_SUBSCRIBER,
        guard.OPERATOR_CLI,
    }
