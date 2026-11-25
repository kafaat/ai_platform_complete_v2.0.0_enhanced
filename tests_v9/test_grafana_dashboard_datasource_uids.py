"""Guard: every datasource a provisioned dashboard references can be resolved.

grafana/dashboards/json/*.json hard-coded ``{"type": "prometheus", "uid": "prometheus"}``,
but grafana/datasources/datasource.yml declares no ``uid``. Grafana generates a random
one, so every panel showed "datasource not found" (measured 2026-11-25 on the Railway
integration environment built from main 7551198a; compose mounts the same files).

The fix does NOT pin the datasource uid: compose persists Grafana's database
(``grafana-data:/var/lib/grafana``), and re-provisioning would rewrite the uid of an
existing install, breaking dashboards operators saved against the old one. Instead each
dashboard selects Prometheus through a ``datasource`` template variable, which resolves
on new and existing installs alike. A reference is valid when it is a declared
``${var}`` of type ``datasource`` or a uid the provisioning file declares.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_DASHBOARDS = _ROOT / "grafana" / "dashboards" / "json"
_DATASOURCES = _ROOT / "grafana" / "datasources" / "datasource.yml"
_BUILTIN = {"grafana", "-- Grafana --", "-- Mixed --", "-- Dashboard --"}
_VAR = re.compile(r"^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?$")


def _referenced_uids(node: object, out: set[str]) -> set[str]:
    if isinstance(node, dict):
        ds = node.get("datasource")
        if isinstance(ds, dict) and isinstance(ds.get("uid"), str):
            out.add(ds["uid"])
        elif isinstance(ds, str):
            # Legacy form: a datasource name (or ${var}) instead of {"type", "uid"}.
            out.add(ds)
        for value in node.values():
            _referenced_uids(value, out)
    elif isinstance(node, list):
        for value in node:
            _referenced_uids(value, out)
    return out


def _datasource_variables(dashboard: dict) -> set[str]:
    variables = (dashboard.get("templating") or {}).get("list") or []
    return {v["name"] for v in variables if isinstance(v, dict) and v.get("type") == "datasource"}


def _provisioned_uids() -> set[str]:
    """Provisioned uids, plus names, which a legacy string reference resolves against."""
    doc = yaml.safe_load(_DATASOURCES.read_text(encoding="utf-8"))
    entries = [d for d in doc.get("datasources", []) if isinstance(d, dict)]
    return {d["uid"] for d in entries if d.get("uid")} | {
        d["name"] for d in entries if d.get("name")
    }


def _unresolved(dashboard: dict, provisioned: set[str]) -> list[str]:
    declared = _datasource_variables(dashboard)
    missing = []
    for uid in sorted(_referenced_uids(dashboard, set()) - _BUILTIN):
        var = _VAR.match(uid)
        if var:
            if var.group(1) not in declared:
                missing.append(f"undeclared datasource variable {uid}")
        elif uid not in provisioned:
            missing.append(f"unprovisioned uid {uid}")
    return missing


def test_dashboards_exist() -> None:
    assert sorted(_DASHBOARDS.glob("*.json")), "no provisioned dashboards found"


def test_every_dashboard_datasource_reference_resolves() -> None:
    provisioned = _provisioned_uids()
    problems = []
    for path in sorted(_DASHBOARDS.glob("*.json")):
        for problem in _unresolved(json.loads(path.read_text(encoding="utf-8")), provisioned):
            problems.append(f"{path.relative_to(_ROOT)}: {problem}")
    assert not problems, problems


def test_existing_prometheus_datasource_keeps_its_generated_uid() -> None:
    # Pinning a uid on the already-provisioned "Prometheus" datasource rewrites it in an
    # existing Grafana database and breaks operator-saved dashboards that point at the old
    # generated uid (Devin review on #1625). A new datasource may still declare a uid.
    doc = yaml.safe_load(_DATASOURCES.read_text(encoding="utf-8"))
    prometheus = [d for d in doc.get("datasources", []) if d.get("name") == "Prometheus"]
    assert len(prometheus) == 1
    assert "uid" not in prometheus[0]


def test_resolution_rules() -> None:
    hard_coded = {"panels": [{"datasource": {"uid": "prometheus"}}]}
    assert _unresolved(hard_coded, set()) == ["unprovisioned uid prometheus"]
    templated = {
        "templating": {"list": [{"name": "datasource", "type": "datasource"}]},
        "panels": [{"targets": [{"datasource": {"uid": "${datasource}"}}]}],
    }
    assert _unresolved(templated, set()) == []
    undeclared = {"panels": [{"datasource": {"uid": "${ds}"}}]}
    assert _unresolved(undeclared, set()) == ["undeclared datasource variable ${ds}"]
    legacy = {"panels": [{"datasource": "Prometheus"}, {"datasource": "Loki"}]}
    assert _unresolved(legacy, {"Prometheus"}) == ["unprovisioned uid Loki"]
