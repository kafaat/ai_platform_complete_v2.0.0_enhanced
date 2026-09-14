"""Measured deployment counterexamples: wrong EXPOSE ports and shared SQLite."""

import copy
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "helm_readiness", ROOT / "scripts/deploy/validate_helm_readiness.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.fixture
def values():
    base = gate.load_yaml(gate.CHART / "values.yaml")
    overlay = gate.load_yaml(gate.CHART / "values-production.yaml")
    return gate.deep_merge(base, overlay)


def test_production_chart_matches_actual_sources(values):
    assert gate.source_contract_errors(values) == []


def test_wrong_port_mutation_is_rejected(values):
    broken = copy.deepcopy(values)
    broken["workloads"]["sahool-raster-service"]["port"] = 8080
    assert any("does not match" in x for x in gate.source_contract_errors(broken))


@pytest.mark.parametrize("change", [{"replicas": 2}, {"persistence": None}])
def test_sqlite_without_single_persistent_owner_is_rejected(values, change):
    broken = copy.deepcopy(values)
    broken["workloads"]["sahool-knowledge-graph"].update(change)
    assert any("SQLite" in x for x in gate.source_contract_errors(broken))
