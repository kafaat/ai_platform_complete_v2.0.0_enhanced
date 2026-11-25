"""Guard: every datasource uid a provisioned dashboard references is provisioned.

grafana/dashboards/json/*.json reference ``{"type": "prometheus", "uid": "prometheus"}``,
but grafana/datasources/datasource.yml declared no ``uid``. Grafana then generated a
random one and every panel showed "datasource not found" (measured 2026-11-25 on the
Railway integration environment built from main 7551198a; compose mounts the same files).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_DASHBOARDS = _ROOT / "grafana" / "dashboards" / "json"
_DATASOURCES = _ROOT / "grafana" / "datasources" / "datasource.yml"
_BUILTIN = {"grafana", "-- Grafana --", "-- Mixed --", "-- Dashboard --"}


def _referenced_uids(node: object, out: set[str]) -> set[str]:
    if isinstance(node, dict):
        ds = node.get("datasource")
        if isinstance(ds, dict) and isinstance(ds.get("uid"), str):
            out.add(ds["uid"])
        for value in node.values():
            _referenced_uids(value, out)
    elif isinstance(node, list):
        for value in node:
            _referenced_uids(value, out)
    return out


def _provisioned_uids() -> set[str]:
    doc = yaml.safe_load(_DATASOURCES.read_text(encoding="utf-8"))
    return {d["uid"] for d in doc.get("datasources", []) if isinstance(d, dict) and d.get("uid")}


def test_dashboards_exist() -> None:
    assert sorted(_DASHBOARDS.glob("*.json")), "no provisioned dashboards found"


def test_every_referenced_datasource_uid_is_provisioned() -> None:
    provisioned = _provisioned_uids()
    missing = []
    for path in sorted(_DASHBOARDS.glob("*.json")):
        refs = _referenced_uids(json.loads(path.read_text(encoding="utf-8")), set())
        for uid in sorted(refs - provisioned - _BUILTIN):
            if uid.startswith("${"):  # template variable, resolved at view time
                continue
            missing.append(f"{path.relative_to(_ROOT)} -> {uid}")
    assert not missing, f"dashboards reference unprovisioned datasource uids: {missing}"


def test_collector_sees_nested_references() -> None:
    sample = {"panels": [{"targets": [{"datasource": {"uid": "a"}}], "datasource": {"uid": "b"}}]}
    assert _referenced_uids(sample, set()) == {"a", "b"}
