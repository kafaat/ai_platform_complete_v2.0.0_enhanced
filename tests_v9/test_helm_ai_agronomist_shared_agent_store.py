"""Helm: a multi-replica ai-agronomist must share its approval/audit store.

``services/ai_agronomist/agent_stores.py`` keeps approvals in process memory unless
``SAHOOL_AGENT_STORE_BACKEND=redis`` and a Redis URL are set. The chart ran two replicas with
neither, so a pending approval created on one pod was invisible to the other and lost on restart.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "sahool"


def _values(name: str) -> dict:
    return yaml.safe_load((CHART / name).read_text(encoding="utf-8")) or {}


def _agronomist(values: dict) -> dict:
    return (values.get("services") or values.get("workloads") or {}).get("sahool-ai-agronomist", {})


@pytest.mark.parametrize(
    "overlay", ["values.yaml", "values-production.yaml", "values-staging.yaml"]
)
def test_more_than_one_replica_uses_the_shared_redis_store(overlay):
    base = _values("values.yaml")
    svc = {**_agronomist(base), **_agronomist(_values(overlay))}
    assert svc, "sahool-ai-agronomist missing from the chart"
    if int(svc.get("replicas", 1)) > 1:
        base_svc = _agronomist(base)
        assert base_svc["env"].get("SAHOOL_AGENT_STORE_BACKEND") == "redis"
        secret_key = base_svc["secretEnv"].get("SAHOOL_AGENT_REDIS_URL")
        assert secret_key, "the Redis URL must come from a secret, not a literal"
        assert secret_key in base["global"]["secretRefs"]


def test_the_store_reads_the_variable_the_chart_sets():
    src = (ROOT / "services" / "ai_agronomist" / "agent_stores.py").read_text(encoding="utf-8")
    assert '"SAHOOL_AGENT_STORE_BACKEND"' in src
    assert '"SAHOOL_AGENT_REDIS_URL"' in src
