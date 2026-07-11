"""WS-E — unit coverage for the consumer-contract gate (deterministic, no services).

Loads the gate by path and exercises its pure helpers with synthetic sources (positive AND
negative) so the gate is proven to CATCH regressions, then asserts it is green on the real tree.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_GATE = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "consumer_contract_gate.py"
_spec = importlib.util.spec_from_file_location("consumer_contract_gate_under_test", _GATE)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)


def test_func_source_strips_docstring_but_keeps_value_strings():
    src = (
        "def agro_gdd():\n"
        '    """the kernel gdd_agro_product stays authoritative"""\n'
        "    return gdd_view(series, x='derived_from')\n"
    )
    isolated = _mod._func_source(src, "agro_gdd")
    assert isolated is not None
    # docstring mention of the forbidden kernel is stripped ...
    assert "gdd_agro_product" not in isolated
    # ... but value-string literals used in code survive.
    assert "gdd_view" in isolated
    assert "derived_from" in isolated


def test_check_func_flags_missing_required():
    text = "def et0_view(state):\n    return {'derived_from': 'canonical_weather_state'}\n"
    violations: list[str] = []
    _mod._check_func(
        violations,
        _mod.CWS,
        text,
        "et0_view",
        required=("derived_from", "canonical_state_id"),
    )
    assert len(violations) == 1
    assert "canonical_state_id" in violations[0]


def test_check_func_flags_forbidden_direct_kernel():
    # A regressed consumer that calls the raw kernel directly (not via the canonical builder).
    text = "def agro_et0():\n    return et0_agro_product(t_min=1, t_max=2)\n"
    violations: list[str] = []
    _mod._check_func(
        violations,
        _mod.WRUNTIME,
        text,
        "agro_et0",
        required=("et0_view",),
        forbidden=("et0_agro_product(",),
    )
    # both the missing-required (et0_view) and the forbidden-kernel are reported.
    assert any("et0_view" in v for v in violations)
    assert any("et0_agro_product(" in v for v in violations)


def test_check_func_missing_function_is_flagged():
    violations: list[str] = []
    _mod._check_func(violations, _mod.WRUNTIME, "def other(): pass\n", "agro_et0")
    assert len(violations) == 1
    assert "not found" in violations[0]


def test_check_func_passes_clean_consumer():
    text = (
        "def agro_et0():\n"
        "    state = build_canonical_weather_state(x=1)\n"
        "    return et0_view(state)\n"
    )
    violations: list[str] = []
    _mod._check_func(
        violations,
        _mod.WRUNTIME,
        text,
        "agro_et0",
        required=("build_canonical_weather_state", "et0_view"),
        forbidden=("et0_agro_product(",),
    )
    assert violations == []


def test_gate_is_green_on_real_tree():
    # The WS-A..D consumers are migrated; the gate must pass on the real repository.
    assert _mod.collect_violations() == []
