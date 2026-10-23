"""Real broker regression for config-scalar expansion of Compose credentials."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "nats" / "start-nats.sh"
PASSWORD_VARS = tuple(
    f"NATS_{name}_PASSWORD"
    for name in (
        "PLATFORM",
        "OUTBOX_WORKER",
        "PLUGIN_WORKER",
        "MODEL_WORKER",
        "ACTUATOR_WORKER",
        "RELAY_WORKER",
        "LEARNING_WORKER",
        "NOTIFICATION",
        "VEGETATION",
    )
)


def _env():
    return {**os.environ, **{name: "testFixtureCredential" for name in PASSWORD_VARS}}


def _binary():
    binary = (
        os.getenv("NATS_SERVER_BIN")
        or os.getenv("NOTIFICATION_TEST_NATS_SERVER")
        or shutil.which("nats-server")
    )
    if not binary:
        if os.getenv("NATS_LEAST_PRIVILEGE_LIVE_REQUIRED") == "1":
            pytest.fail("Real NATS binary required for password expansion proof")
        pytest.skip("Real NATS binary unavailable")
    return binary


def _protocol(port, password):
    with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
        stream = connection.makefile("rb")
        assert stream.readline().startswith(b"INFO ")
        connect = json.dumps({"user": "fixture-user", "pass": password, "verbose": True})
        connection.sendall(f"CONNECT {connect}\r\nPING\r\n".encode())
        first = stream.readline()
        if first.startswith(b"-ERR"):
            return False
        assert first == b"+OK\r\n", "Unexpected broker protocol response"
        assert stream.readline() == b"PONG\r\n", "Broker did not acknowledge authenticated PING"
        return True


@pytest.mark.integration
@pytest.mark.parametrize(
    "password",
    [
        "3e0f9c2b7a",
        "08abcdef0123456789",
        "123456789",
        "true",
        "false",
        "credential._~-42",
    ],
    ids=["exponent-hex", "leading-zero-hex", "numeric", "true-scalar", "false-scalar", "url-safe"],
)
def test_real_broker_preserves_password_as_string(tmp_path, password):
    binary = _binary()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    config = tmp_path / "broker.conf"
    config.write_text(
        'authorization { users: [{ user: "fixture-user", password: $NATS_PLUGIN_WORKER_PASSWORD }] }\n',
        encoding="utf-8",
    )
    env = _env()
    env["NATS_PLUGIN_WORKER_PASSWORD"] = password
    log = tmp_path / "broker.log"
    with log.open("wb") as output:
        proc = subprocess.Popen(
            ["sh", str(START), binary, "-a", "127.0.0.1", "-p", str(port), "-c", str(config)],
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 5
            while "Server is ready" not in log.read_text():
                assert proc.poll() is None, "Broker exited before becoming ready"
                assert time.monotonic() < deadline, "Broker readiness timed out"
                time.sleep(0.02)
            assert _protocol(port, password), "Original credential was not accepted"
            assert not _protocol(port, "known-wrong-credential"), (
                "Incorrect credential was accepted"
            )
            # Config quoting is a broker implementation detail; clients must keep raw values.
            assert not _protocol(port, json.dumps(password)), (
                "Quoted client credential was accepted"
            )
        finally:
            proc.terminate()
            proc.wait(timeout=5)
    assert password not in log.read_text(), "Broker logs disclosed a credential"


@pytest.mark.unit
@pytest.mark.parametrize(
    "invalid",
    [
        None,
        "",
        "secret@host",
        "secret:other",
        "secret/other",
        'secret"quote',
        "secret\\escape",
        "secret\nline",
        "secret\n",
        "secret space",
        "secret$variable",
    ],
)
def test_bootstrap_rejects_missing_or_url_unsafe_password_without_disclosure(invalid):
    env = _env()
    if invalid is None:
        env.pop("NATS_PLUGIN_WORKER_PASSWORD")
    else:
        env["NATS_PLUGIN_WORKER_PASSWORD"] = invalid
    result = subprocess.run(
        ["sh", str(START), "sh", "-c", "echo SERVER_EXECUTED"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "SERVER_EXECUTED" not in result.stdout
    assert "NATS_PLUGIN_WORKER_PASSWORD" in result.stderr
    if invalid:
        assert invalid not in result.stdout + result.stderr


@pytest.mark.unit
def test_compose_broker_uses_password_bootstrap():
    import yaml

    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text())
    broker = compose["services"]["sahool-nats"]
    assert broker["entrypoint"] == ["/bin/sh", "/etc/nats/start-nats.sh", "nats-server"]
    assert "./nats/start-nats.sh:/etc/nats/start-nats.sh:ro" in broker["volumes"]
    assert broker["command"] == ["-c", "/etc/nats/nats.conf"]
    # Raw credentials belong to clients; only the broker bootstrap may quote them.
    for name in PASSWORD_VARS:
        assert broker["environment"][name].startswith("${" + name + ":?")
