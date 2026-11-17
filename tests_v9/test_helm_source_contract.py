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


def test_a_bound_port_counts_without_expose():
    """W3-09: field-management binds uvicorn on 8000 and has no EXPOSE line.

    Adding EXPOSE only for this gate would rebuild that service on Railway; the port the image
    actually runs on is read from its CMD instead, never from the chart values under test.
    """
    assert gate.dockerfile_ports(
        'CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]\n'
    ) == {8000}
    assert gate.dockerfile_ports("CMD uvicorn main:app --port=7000\n") == {7000}
    assert gate.dockerfile_ports("EXPOSE 9000\nCMD python main.py\n") == {9000}
    assert gate.dockerfile_ports("RUN pip download --port 1234\n") == set(), "only CMD/ENTRYPOINT"
    source = (ROOT / "services/field-management-service/Dockerfile").read_text(encoding="utf-8")
    assert "EXPOSE" not in source.replace("# ", ""), "the Dockerfile stays unchanged by the chart"
    assert gate.dockerfile_ports(source) == {8000}


def test_a_chart_port_the_image_does_not_bind_is_still_rejected(values):
    broken = copy.deepcopy(values)
    broken["workloads"]["sahool-field-management"]["port"] = 8001
    assert any(
        "sahool-field-management" in x and "does not match" in x
        for x in gate.source_contract_errors(broken)
    )
