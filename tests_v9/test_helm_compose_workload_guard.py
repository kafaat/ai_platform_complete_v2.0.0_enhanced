"""Witness for scripts/ci/helm_compose_workload_guard.py (W3-09).

The committed tree is clean: every default-profile compose service is a Helm workload or a
ledgered exclusion, and every workload renders the variables compose requires or excuses
them. The negative controls run the same ``audit`` on copies of the committed inputs with
one defect planted each, so a guard that stopped looking would turn them green.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "ci" / "helm_compose_workload_guard.py"


def _guard():
    spec = importlib.util.spec_from_file_location("_helm_compose_workload_guard", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GUARD = _guard()


@pytest.fixture
def inputs() -> tuple[dict, dict, dict]:
    compose = yaml.safe_load(GUARD.COMPOSE.read_text(encoding="utf-8"))
    values = yaml.safe_load(GUARD.VALUES.read_text(encoding="utf-8"))
    ledger = json.loads(GUARD.LEDGER.read_text(encoding="utf-8"))
    return compose, values, ledger


def test_the_committed_tree_is_clean() -> None:
    result = subprocess.run(
        [sys.executable, str(TOOL)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "helm_compose_workload_guard: PASS" in result.stdout


def test_coverage_is_a_set_equality(inputs) -> None:
    compose, values, ledger = inputs
    services = set(GUARD.default_profile_services(compose))
    workloads = set(values["workloads"])
    excluded = {k for k in ledger["excluded"] if not k.startswith("$")}
    assert services, "the guard read no compose service"
    assert workloads <= services, "every workload names a compose service"
    assert workloads.isdisjoint(excluded), "a ported service leaves the ledger"
    assert services == workloads | excluded


def test_a_service_in_neither_list_blocks(inputs) -> None:
    compose, values, ledger = inputs
    compose = copy.deepcopy(compose)
    compose["services"]["sahool-new-service"] = {"image": "example/new:1.0.0"}
    problems, _ = GUARD.audit(compose, values, ledger)
    assert any(
        p.startswith("sahool-new-service: compose service with no Helm workload") for p in problems
    ), problems


def test_a_profiled_service_is_out_of_scope(inputs) -> None:
    compose, values, ledger = inputs
    compose = copy.deepcopy(compose)
    compose["services"]["sahool-optional"] = {"image": "example/x:1.0.0", "profiles": ["lab"]}
    problems, _ = GUARD.audit(compose, values, ledger)
    assert problems == []


def test_a_workload_that_drops_a_required_variable_blocks(inputs) -> None:
    compose, values, ledger = inputs
    values = copy.deepcopy(values)
    # DATABASE_URL is compose-required for sahool-platform and not excused.
    values["workloads"]["sahool-platform"]["secretEnv"].pop("DATABASE_URL")
    problems, _ = GUARD.audit(compose, values, ledger)
    assert any(p.startswith("sahool-platform: compose requires DATABASE_URL") for p in problems), (
        problems
    )


def test_a_ledger_entry_for_a_ported_service_is_stale(inputs) -> None:
    compose, values, ledger = inputs
    ledger = copy.deepcopy(ledger)
    ledger["excluded"]["sahool-platform"] = {"category": "not_yet_ported", "reason": "x"}
    problems, _ = GUARD.audit(compose, values, ledger)
    assert "sahool-platform: stale ledger entry — the chart now declares this workload" in problems


def test_a_ledger_entry_for_a_removed_service_is_stale(inputs) -> None:
    compose, values, ledger = inputs
    ledger = copy.deepcopy(ledger)
    ledger["excluded"]["sahool-gone"] = {"category": "not_yet_ported", "reason": "x"}
    problems, _ = GUARD.audit(compose, values, ledger)
    assert "sahool-gone: stale ledger entry — not a default-profile compose service" in problems


def test_an_entry_needs_a_declared_category_and_a_reason(inputs) -> None:
    compose, values, ledger = inputs
    ledger = copy.deepcopy(ledger)
    name = next(k for k in ledger["excluded"] if not k.startswith("$"))
    ledger["excluded"][name] = {"category": "because", "reason": " "}
    problems, _ = GUARD.audit(compose, values, ledger)
    assert f"{name}: ledger category 'because' is not declared" in problems
    assert f"{name}: ledger entry has no reason" in problems


def test_an_excuse_for_a_rendered_variable_is_stale(inputs) -> None:
    compose, values, ledger = inputs
    values = copy.deepcopy(values)
    values["workloads"]["sahool-rag-retrieval"]["secretEnv"]["QDRANT_API_KEY"] = "agentToken"
    problems, _ = GUARD.audit(compose, values, ledger)
    assert (
        "sahool-rag-retrieval: stale excuse for QDRANT_API_KEY — the workload now renders it"
        in problems
    )


def test_an_excuse_for_a_variable_compose_no_longer_requires_is_stale(inputs) -> None:
    compose, values, ledger = inputs
    ledger = copy.deepcopy(ledger)
    ledger["env_excused"]["sahool-rag-retrieval"]["NOT_A_COMPOSE_VAR"] = "x"
    problems, _ = GUARD.audit(compose, values, ledger)
    assert (
        "sahool-rag-retrieval: stale excuse for NOT_A_COMPOSE_VAR — compose no longer requires it"
        in problems
    )


def test_a_workload_without_a_compose_service_blocks(inputs) -> None:
    compose, values, ledger = inputs
    values = copy.deepcopy(values)
    values["workloads"]["sahool-orphan"] = {"enabled": True, "env": {}, "secretEnv": {}}
    problems, _ = GUARD.audit(compose, values, ledger)
    assert any(
        p.startswith("sahool-orphan: Helm workload with no default-profile compose")
        for p in problems
    )


def test_reading_nothing_fails_closed(inputs) -> None:
    _, values, ledger = inputs
    problems, _ = GUARD.audit({"services": {}}, values, ledger)
    assert any("no default-profile service was read" in p for p in problems)


@pytest.mark.parametrize(
    ("value", "required"),
    [
        ("${DATABASE_URL:?DATABASE_URL required}", True),
        ("${X?missing}", True),
        ("redis://u:${PW:?PW required}@host:6379/0", True),
        ("${DSN:-postgresql://u:${PW:?PW required}@db/x}", True),
        ("${JWT_PUBLIC_KEY:-}", False),
        ("plain", False),
    ],
)
def test_required_means_a_question_mark_interpolation(value: str, required: bool) -> None:
    for environment in ({"V": value}, [f"V={value}"]):
        assert GUARD.required_variables({"environment": environment}) == (
            {"V"} if required else set()
        )


def test_sahool_env_is_always_rendered() -> None:
    template = (ROOT / "helm" / "sahool" / "templates" / "deployments.yaml").read_text(
        encoding="utf-8"
    )
    assert "- name: SAHOOL_ENV" in template, (
        "ALWAYS_RENDERED claims the template emits SAHOOL_ENV for every workload"
    )
    assert GUARD.rendered_variables({}) == {"SAHOOL_ENV"}
