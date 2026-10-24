"""Behavioural receipt policy: a successful process is not sufficient broker evidence.

Docker transport is replaced by deterministic command responses here. These tests
exercise the real acceptance control flow and receipt writer; live Compose remains
its own CI job. Mutation plants remove the actual source decisions, not fixtures.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/run_nats_compose_acceptance.py"
SHA = "5f730646a112ceb770fb89ce194c259e94921f30"


@pytest.fixture
def acceptance(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("_nats_compose_receipt_policy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "source"
    for relative in (
        "nats/nats.conf",
        "nats/start-nats.sh",
        "scripts/tls/ensure_service_tls.sh",
        "docker-compose.v9.yml",
    ):
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    report = tmp_path / "receipt"
    state = {"sha": SHA, "restarts": 0, "health": "healthy", "accept_wrong": False}
    commands = []

    def command(argv, **kwargs):
        commands.append(argv)
        if argv[0] == "git":
            return state["sha"] if "rev-parse" in argv else ""
        if argv[0] == "sh":
            tls = Path(kwargs["env"]["TLS_DIR"])
            (tls / "ca").mkdir(parents=True)
            (tls / "ca/ca.pem").write_text("fixture CA", encoding="utf-8")
            return ""
        if argv[:3] == ["docker", "context", "inspect"]:
            return "unix:///fixture-docker.sock"
        if argv[:2] == ["docker", "version"]:
            return "fixture-daemon-version"
        if argv[:3] == ["docker", "compose", "version"]:
            return "fixture-compose-version"
        if argv[:2] == ["docker", "inspect"]:
            if "{{.RestartCount}}" in argv:
                return str(state["restarts"])
            return json.dumps({"Status": "running", "Health": {"Status": state["health"]}})
        if "port" in argv:
            return "127.0.0.1:14222"
        if "ps" in argv:
            return "owned-fixture-container"
        return ""

    def authenticate(_port, _ca, password):
        return (
            state["accept_wrong"] and password == "knownWrongDisposableCredential"
        ) or password.startswith("3e0")

    monkeypatch.setattr(module, "command", command)
    monkeypatch.setattr(module, "authenticate", authenticate)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/fixture/" + name)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--repo", str(source), "--expected-sha", SHA, "--report", str(report)],
    )

    def run():
        code = module.main()
        receipt = json.loads((report / "result.json").read_text(encoding="utf-8"))
        return code, receipt, commands

    return state, run


def test_healthy_exact_source_broker_publishes_scoped_receipt(acceptance):
    _state, run = acceptance
    code, receipt, commands = run()
    assert code == 0 and receipt["status"] == "PASS"
    assert receipt["source_sha"] == SHA
    assert receipt["scope"] == "isolated NATS Compose slice; not complete SAHOOL stack"
    assert receipt["health"] == "healthy" and receipt["restart_count"] == 0
    assert receipt["probes"]["raw_password"] == "accepted"
    assert receipt["probes"]["wrong_password"] == "rejected"
    assert receipt["probes"]["quoted_password"] == "rejected"
    assert receipt["cleanup"] == "PASS"
    assert any("down" in command for command in commands)


def test_restarted_broker_cannot_publish_pass(acceptance):
    state, run = acceptance
    state["restarts"] = 1
    code, receipt, _commands = run()
    assert code == 1 and receipt["status"] == "FAIL"
    assert receipt["reason"] == "AssertionError"
    assert receipt["detail"] == "Broker restarted"
    assert receipt["cleanup"] == "PASS"


def test_wrong_source_sha_cannot_publish_pass(acceptance):
    state, run = acceptance
    state["sha"] = "0" * 40
    code, receipt, commands = run()
    assert code == 1 and receipt["status"] == "FAIL"
    assert receipt["detail"] == "Source HEAD differs from requested SHA"
    assert not any("up" in command for command in commands)


def test_unhealthy_broker_cannot_publish_pass(acceptance):
    state, run = acceptance
    state["health"] = "unhealthy"
    code, receipt, _commands = run()
    assert code == 1 and receipt["status"] == "FAIL"
    assert receipt["reason"] == "AssertionError"
    assert receipt["cleanup"] == "PASS"


def test_wrong_password_acceptance_cannot_publish_pass(acceptance):
    state, run = acceptance
    state["accept_wrong"] = True
    code, receipt, _commands = run()
    assert code == 1 and receipt["status"] == "FAIL"
    assert receipt["reason"] == "AssertionError"
    assert receipt["cleanup"] == "PASS"
