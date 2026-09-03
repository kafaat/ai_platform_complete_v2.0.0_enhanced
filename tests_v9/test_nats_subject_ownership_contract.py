"""Fail-closed inventory for the open NATS ownership gaps."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/architecture/nats_subject_ownership_contract.json"
SUBJECT = "sahool.actuator.dispatch.requested"


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _python_sources() -> list[Path]:
    return sorted((ROOT / "services").rglob("*.py")) + sorted((ROOT / "agents").rglob("*.py"))


def test_compose_nats_clients_match_the_declared_inventory() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    connected = []
    for name, service in compose["services"].items():
        environment = service.get("environment") or {}
        if isinstance(environment, dict) and any(
            "NATS" in str(key) or "nats://" in str(value) for key, value in environment.items()
        ):
            connected.append(name)
    assert sorted(connected) == sorted(_contract()["connected_services"])


def test_actuator_dispatch_has_one_publisher_and_no_repository_consumer() -> None:
    publishers: list[str] = []
    consumers: list[str] = []
    literal_sites: list[str] = []
    for path in _python_sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if SUBJECT not in text:
            continue
        literal_sites.append(str(path.relative_to(ROOT)))
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            if node.args[0].value != SUBJECT:
                continue
            if node.func.attr == "publish":
                publishers.append(str(path.relative_to(ROOT)))
            if node.func.attr in {"subscribe", "pull_subscribe"}:
                consumers.append(str(path.relative_to(ROOT)))
    # The platform publisher calls a wrapper whose literal is the first argument.
    worker = ROOT / "services/sahool-platform/api/phase_runtime_workers.py"
    assert SUBJECT in worker.read_text(encoding="utf-8")
    assert literal_sites == ["services/sahool-platform/api/phase_runtime_workers.py"]
    assert not consumers
    gap = _contract()["gaps"]["AGENT-TO-ACTUATOR-ADAPTER-ABSENT"]
    assert gap["status"] == "OPEN"
    assert gap["consumers"] == []
    # Direct AST publishers may be empty because the production call uses _publish_nats;
    # there must never be a second direct publisher hidden elsewhere.
    assert len(set(publishers)) <= 1


def test_plugin_subject_transform_is_declared_as_an_open_divergence() -> None:
    worker = (ROOT / "services/sahool-platform/api/phase_runtime_workers.py").read_text(
        encoding="utf-8"
    )
    hooks = (ROOT / "shared/marketplace_ecosystem_phase12.py").read_text(encoding="utf-8")
    notifications = (ROOT / "agents/notification/agent.py").read_text(encoding="utf-8")
    assert 'f"sahool.{str(row[' in worker
    assert '"field.updated"' in hooks
    assert '("sahool.events.>", "notif_domain_events")' in notifications
    gap = _contract()["gaps"]["NATS-SUBJECT-NAMESPACE-CONTRACT-DIVERGENCE"]
    assert gap["status"] == "OPEN"


def test_nats_configuration_still_has_no_authentication_or_subject_acl() -> None:
    config = (ROOT / "nats/nats.conf").read_text(encoding="utf-8").lower()
    for token in ("authorization", "accounts", "users", "nkeys", "permissions"):
        assert token not in config
    assert _contract()["gaps"]["NATS-AUTHORIZATION-NOT-ENFORCED"]["status"] == "OPEN"
