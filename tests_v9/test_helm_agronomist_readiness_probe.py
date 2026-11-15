"""The agronomist's Kubernetes readiness probe must not gate rollout on the RAG claim (#1474).

Since #1466 the agronomist /readyz answers 503 while no embedding profile is bound. The chart's
readiness probe used /readyz for every workload, and no Helm or compose value binds a profile,
so a default `helm upgrade --atomic` would hold the pods unready and roll the release back
(independent review of #1474). /readyz keeps its meaning for monitoring and certification; the
probe uses /healthz for this one service, every other workload keeps /readyz.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "sahool"


def _values() -> dict:
    return yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))


def _services(values: dict) -> dict:
    for key in ("services", "workloads"):
        if isinstance(values.get(key), dict) and "sahool-ai-agronomist" in values[key]:
            return values[key]
    raise AssertionError("sahool-ai-agronomist not found in helm/sahool/values.yaml")


def test_the_readiness_probe_path_is_per_service_with_readyz_as_default() -> None:
    template = (CHART / "templates" / "deployments.yaml").read_text(encoding="utf-8")
    assert '$svc.readinessPath | default "/readyz"' in template
    assert "path: /readyz" not in template, (
        "a hard-coded /readyz probe path would put the agronomist back on a 503 probe"
    )


def test_the_agronomist_probe_uses_healthz_and_others_keep_readyz() -> None:
    services = _services(_values())
    assert services["sahool-ai-agronomist"].get("readinessPath") == "/healthz"
    others = [
        name
        for name, svc in services.items()
        if isinstance(svc, dict) and name != "sahool-ai-agronomist"
    ]
    assert others
    for name in others:
        assert services[name].get("readinessPath") in (None, "/readyz"), name


def test_environment_overlays_do_not_put_the_agronomist_probe_back_on_readyz() -> None:
    for overlay in ("values-production.yaml", "values-staging.yaml"):
        data = yaml.safe_load((CHART / overlay).read_text(encoding="utf-8")) or {}
        for key in ("services", "workloads"):
            svc = (data.get(key) or {}).get("sahool-ai-agronomist") or {}
            assert svc.get("readinessPath") in (None, "/healthz"), overlay
