#!/usr/bin/env python3
"""Isolated SAHOOL NATS Compose acceptance; no production credentials required."""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import ssl
import subprocess
import tempfile
import time
from pathlib import Path

if not __debug__:
    raise SystemExit("Optimized Python disables acceptance assertions; run without -O")


def interrupted(signum, _frame):
    raise InterruptedError(f"Interrupted by signal {signum}")


PASSWORDS = (
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


def command(argv, **kwargs):
    return subprocess.run(
        argv, check=True, capture_output=True, text=True, encoding="utf-8", timeout=120, **kwargs
    ).stdout.strip()


def authenticate(port, ca, password):
    with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
        # NATS sends INFO before the TLS upgrade (not direct TLS on connect).
        info = bytearray()
        while not info.endswith(b"\r\n"):
            chunk = raw.recv(1)
            if not chunk:
                raise RuntimeError("Broker closed before INFO")
            info.extend(chunk)
            if len(info) > 16384:
                raise RuntimeError("Oversized INFO")
        assert json.loads(info[5:])["tls_required"] is True
        context = ssl.create_default_context(cafile=str(ca))
        with context.wrap_socket(raw, server_hostname="sahool-nats") as connection:
            stream = connection.makefile("rb")
            connect = {
                "user": "sahool-plugin-runtime-worker",
                "pass": password,
                "verbose": True,
                "pedantic": True,
            }
            connection.sendall(("CONNECT " + json.dumps(connect) + "\r\nPING\r\n").encode())
            line = stream.readline(16384)
            if line.startswith(b"-ERR"):
                assert b"Authorization Violation" in line
                return False
            assert line == b"+OK\r\n", "Unexpected authentication response"
            assert stream.readline(16384) == b"PONG\r\n", "Missing authenticated PONG"
            return True


class PrerequisiteUnavailable(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    repo, report = args.repo.resolve(), args.report.resolve()
    if not re.fullmatch("[0-9a-f]{40}", args.expected_sha):
        parser.error("--expected-sha must be a full lowercase SHA")
    report.mkdir(parents=True, exist_ok=False)
    result = {
        "status": "BLOCKED",
        "expected_sha": args.expected_sha,
        "scope": "isolated NATS Compose slice; not complete SAHOOL stack",
    }
    temp = None
    compose = None
    env = None
    credentials = []
    previous_handlers = {}
    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.signal(signum, interrupted)
        if not shutil.which("docker") or not shutil.which("openssl"):
            result["reason"] = "docker and openssl executables required"
            raise PrerequisiteUnavailable
        if os.getenv("DOCKER_HOST") or os.getenv("DOCKER_CONTEXT"):
            raise RuntimeError(
                "Use a local Docker daemon on the execution host; remote bind mounts are unsafe here"
            )
        endpoint = command(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]
        )
        if not endpoint.startswith("unix://"):
            raise RuntimeError("Local Unix Docker endpoint required")
        result["docker_version"] = command(["docker", "version", "--format", "{{.Server.Version}}"])
        result["compose_version"] = command(["docker", "compose", "version", "--short"])
        actual = command(["git", "-C", str(repo), "rev-parse", "HEAD"])
        assert actual == args.expected_sha, "Source HEAD differs from requested SHA"
        command(
            [
                "git",
                "-C",
                str(repo),
                "diff",
                "--exit-code",
                "HEAD",
                "--",
                "nats/nats.conf",
                "nats/start-nats.sh",
                "scripts/tls/ensure_service_tls.sh",
                "docker-compose.v9.yml",
            ]
        )
        inputs = [
            "nats/nats.conf",
            "nats/start-nats.sh",
            "scripts/tls/ensure_service_tls.sh",
            "docker-compose.v9.yml",
        ]
        result["source_sha"] = actual
        result["input_sha256"] = {
            p: hashlib.sha256((repo / p).read_bytes()).hexdigest() for p in inputs
        }
        # Match the source's broker image, rather than silently substituting another version.
        source = (repo / "docker-compose.v9.yml").read_text(encoding="utf-8")
        match = re.search(r"^  sahool-nats:\n    image: ([^\n]+)", source, re.MULTILINE)
        assert match and re.fullmatch(r"nats:[\w.-]+@sha256:[0-9a-f]{64}", match[1])
        result["image"] = match[1]
        temp = tempfile.TemporaryDirectory(prefix="sahool-nats-compose-")
        root = Path(temp.name)
        tls = root / "tls"
        tls.mkdir()
        env = {
            **os.environ,
            "TLS_DIR": str(tls),
            "TLS_CODE": "NATS",
            "TLS_SERVICE_HOST": "sahool-nats",
            "SAHOOL_ENV": "test",
        }
        command(["sh", str(repo / "scripts/tls/ensure_service_tls.sh")], env=env)
        credentials = ["3e0" + secrets.token_hex(16) for _ in PASSWORDS]
        password_env = {
            f"NATS_{key}_PASSWORD": value for key, value in zip(PASSWORDS, credentials, strict=True)
        }
        env.update(password_env)
        config = {
            "services": {
                "nats": {
                    "image": result["image"],
                    "entrypoint": ["/bin/sh", "/etc/nats/start-nats.sh", "nats-server"],
                    "command": ["-c", "/etc/nats/nats.conf"],
                    "environment": {name: "${" + name + ":?required}" for name in password_env},
                    "volumes": [
                        f"{repo}/nats/nats.conf:/etc/nats/nats.conf:ro",
                        f"{repo}/nats/start-nats.sh:/etc/nats/start-nats.sh:ro",
                        f"{tls}/server:/etc/nats/tls:ro",
                        "jetstream:/data/jetstream",
                    ],
                    "ports": ["127.0.0.1::4222"],
                    "restart": "on-failure",
                    "security_opt": ["no-new-privileges:true"],
                    "healthcheck": {
                        "test": ["CMD-SHELL", "wget -qO- http://localhost:8222/healthz || exit 1"],
                        "interval": "2s",
                        "timeout": "2s",
                        "retries": 20,
                    },
                }
            },
            "volumes": {"jetstream": {}},
        }
        config_path = root / "compose.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        project = "sahool-nats-lab-" + secrets.token_hex(6)
        result["project"] = project
        compose = ["docker", "compose", "-p", project, "-f", str(config_path)]
        command(compose + ["up", "-d", "--wait", "--wait-timeout", "75"], env=env)
        cid = command(compose + ["ps", "-q", "nats"], env=env)
        port_text = command(compose + ["port", "nats", "4222"], env=env)
        port = int(port_text.rsplit(":", 1)[1])
        ca = tls / "ca/ca.pem"
        assert authenticate(port, ca, password_env["NATS_PLUGIN_WORKER_PASSWORD"])
        assert not authenticate(port, ca, "knownWrongDisposableCredential")
        assert not authenticate(port, ca, json.dumps(password_env["NATS_PLUGIN_WORKER_PASSWORD"]))
        time.sleep(3)
        state = json.loads(command(["docker", "inspect", "--format", "{{json .State}}", cid]))
        restarts = int(command(["docker", "inspect", "--format", "{{.RestartCount}}", cid]))
        assert state["Status"] == "running" and state["Health"]["Status"] == "healthy"
        assert restarts == 0, "Broker restarted"
        result.update(
            status="PASS",
            health="healthy",
            restart_count=restarts,
            probes={
                "raw_password": "accepted",
                "wrong_password": "rejected",
                "quoted_password": "rejected",
                "tls_ca_and_hostname": "verified",
            },
        )
    except PrerequisiteUnavailable:
        pass
    except Exception as exc:
        result["status"] = "FAIL"
        result["reason"] = type(exc).__name__
        detail = str(exc)
        for value in credentials:
            detail = detail.replace(value, "[REDACTED]")
        result["detail"] = detail[:2000]
        # Avoid serializing command environments or errors containing credentials.
    finally:
        # A repeated termination request must not interrupt bounded teardown.
        for signum in previous_handlers:
            signal.signal(signum, signal.SIG_IGN)
        if compose:
            try:
                logs = command(compose + ["logs", "--no-color"], env=env)
                for value in credentials:
                    logs = logs.replace(value, "[REDACTED]")
                (report / "broker.log").write_text(logs + "\n", encoding="utf-8")
            except Exception:
                result["log_collection"] = "failed"
            try:
                command(
                    compose + ["down", "--volumes", "--remove-orphans", "--timeout", "10"], env=env
                )
                result["cleanup"] = "PASS"
            except Exception:
                result["cleanup"] = "FAIL"
                result["status"] = "FAIL"
        if temp:
            temp.cleanup()
        (report / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
