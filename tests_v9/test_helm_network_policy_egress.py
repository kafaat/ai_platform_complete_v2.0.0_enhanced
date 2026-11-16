"""Helm NetworkPolicy: opt-in public egress and caller-only ingress (W3-09).

Before W3-09 the namespace default policy let every pod open TCP 443 to any address,
including the gateway, the migration Job and workloads that call no external provider.
Public HTTPS is now rendered by one policy, ``sahool-public-https-egress``, that selects
only the workloads declaring ``publicHttpsEgress: true``; the global
``networkPolicy.allowPublicHttpsEgress`` flag still withdraws it from all of them.

A workload with no auth of its own and no gateway route can be ``internalOnly``: it
admits only its ``internalCallers``. The structural checks run everywhere; the render
checks need the helm binary and are skipped without it.
"""

from __future__ import annotations

import copy
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "sahool"
TEMPLATE = CHART / "templates" / "networkpolicy.yaml"


def _validator():
    spec = importlib.util.spec_from_file_location(
        "validate_helm_readiness_np", ROOT / "scripts" / "deploy" / "validate_helm_readiness.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _validator()

# Which workloads call an external provider over HTTPS, and which one. A workload joins
# this map with the code that makes the call; nothing else gets public egress.
_EXPECTED_PUBLIC_EGRESS = {
    "sahool-platform": "Open-Meteo / MET Norway (services/sahool-platform/api/connectors)",
    "sahool-raster-service": "Copernicus Data Space (CDSE_CLIENT_ID/SECRET)",
    "sahool-ai-agronomist": "hosted model providers when AI_PROVIDER is openrouter/anthropic",
    "sahool-weather-service": "Open-Meteo forecast/archive (services/weather-service/open_meteo.py)",
}

# Workloads that admit only named callers (no gateway), with those callers.
_EXPECTED_INTERNAL_ONLY: dict[str, list[str]] = {
    # No auth of its own; sahool-platform's weather_service_client is the in-chart caller.
    "sahool-weather-service": ["sahool-platform"],
}


def _production_values() -> dict:
    base = VALIDATOR.load_yaml(CHART / "values.yaml")
    overlay = VALIDATOR.load_yaml(CHART / "values-production.yaml")
    return VALIDATOR.deep_merge(base, overlay)


def test_public_egress_is_exactly_the_declared_set() -> None:
    workloads = _production_values()["workloads"]
    declared = {n for n, s in workloads.items() if s.get("enabled") and s.get("publicHttpsEgress")}
    assert declared == set(_EXPECTED_PUBLIC_EGRESS), (
        "public HTTPS egress is granted per workload, with the provider it reaches; "
        f"declared {sorted(declared)}"
    )


def test_internal_only_workloads_admit_exactly_their_callers() -> None:
    workloads = _production_values()["workloads"]
    internal = {n: s.get("internalCallers") for n, s in workloads.items() if s.get("internalOnly")}
    assert internal == _EXPECTED_INTERNAL_ONLY


def test_the_validator_accepts_the_committed_values() -> None:
    assert VALIDATOR.network_policy_errors(_production_values()) == []


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"internalOnly": True, "gatewayOnly": False, "internalCallers": []}, "internalOnly needs"),
        ({"internalOnly": True, "gatewayOnly": True}, "not both"),
        ({"internalCallers": ["sahool-no-such-workload"]}, "not an enabled workload"),
        ({"publicHttpsEgress": "yes"}, "must be true or false"),
    ],
)
def test_the_validator_refuses_a_broken_policy_declaration(change: dict, expected: str) -> None:
    values = copy.deepcopy(_production_values())
    values["workloads"]["sahool-raster-service"].update(change)
    errors = VALIDATOR.network_policy_errors(values)
    assert any(expected in e for e in errors), errors


def test_internal_callers_without_a_restriction_are_refused() -> None:
    values = copy.deepcopy(_production_values())
    values["workloads"]["sahool-rag-retrieval"]["internalCallers"] = ["sahool-platform"]
    errors = VALIDATOR.network_policy_errors(values)
    assert any("has no effect" in e for e in errors), errors


def test_the_default_policy_carries_no_public_egress() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    default, rest = text.split("name: sahool-public-https-egress", 1)
    assert "0.0.0.0/0" not in default, (
        "a public ipBlock in the namespace default policy reopens 443 for every pod, "
        "the gateway and the migration Job included"
    )
    assert "if and .Values.networkPolicy.allowPublicHttpsEgress $publicHttps" in text, (
        "the global flag must still withdraw public egress from every workload"
    )
    assert "$workload.publicHttpsEgress" in text and "operator: In" in rest


def test_the_template_refuses_an_internal_only_workload_without_callers() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "internalOnly needs internalCallers" in text and "fail (printf" in text


needs_helm = pytest.mark.skipif(shutil.which("helm") is None, reason="helm binary not installed")


def _render(*extra: str) -> list[dict]:
    result = subprocess.run(
        [
            "helm",
            "template",
            "sahool",
            str(CHART),
            "-f",
            str(CHART / "values.yaml"),
            "-f",
            str(CHART / "values-production.yaml"),
            *extra,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return [d for d in yaml.safe_load_all(result.stdout) if d]


@needs_helm
def test_helm_render_grants_public_egress_only_to_declared_workloads() -> None:
    policies = {d["metadata"]["name"]: d for d in _render() if d.get("kind") == "NetworkPolicy"}
    default = policies["sahool-default-deny"]["spec"]
    assert all("ipBlock" not in peer for rule in default["egress"] for peer in rule["to"])
    public = policies["sahool-public-https-egress"]["spec"]
    selected = set(public["podSelector"]["matchExpressions"][0]["values"])
    assert selected == set(_EXPECTED_PUBLIC_EGRESS)
    assert public["egress"][0]["ports"] == [{"protocol": "TCP", "port": 443}]


@needs_helm
def test_helm_render_without_public_egress_renders_no_public_policy() -> None:
    docs = _render("--set", "networkPolicy.allowPublicHttpsEgress=false")
    names = {d["metadata"]["name"] for d in docs if d.get("kind") == "NetworkPolicy"}
    assert "sahool-public-https-egress" not in names


@needs_helm
def test_helm_render_internal_only_workloads_admit_only_their_callers() -> None:
    policies = {d["metadata"]["name"]: d for d in _render() if d.get("kind") == "NetworkPolicy"}
    excluded = policies["sahool-internal-allow"]["spec"]["podSelector"]["matchExpressions"][0]
    for name, callers in _EXPECTED_INTERNAL_ONLY.items():
        policy = policies[f"{name}-internal-only"]["spec"]
        sources = {
            peer["podSelector"]["matchLabels"]["app.kubernetes.io/component"]
            for rule in policy["ingress"]
            for peer in rule["from"]
        }
        assert sources == set(callers), f"{name} must admit only {callers}: {sources}"
        assert name in excluded["values"], f"the namespace-wide allow must exclude {name}"
