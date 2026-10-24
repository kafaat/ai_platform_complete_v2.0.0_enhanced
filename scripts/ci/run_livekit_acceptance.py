#!/usr/bin/env python3
"""Run actual pinned self-hosted SFU admission; publish only sanitized receipts.

Requires Docker on a disposable Linux runner. The synthetic platform authority is
not evidence of production RLS. No Arabic inference or TURN/network claim follows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_NORMAL = {
    "initial_join",
    "actual_refreshed_token",
    "tenant_ownership_denied",
    "field_authorization_denied",
    "tenant_rooms_isolated",
    "room_admin_denied",
    "agent_dispatch_denied",
    "fresh_rejoin_after_delete_denied",
    "refreshed_rejoin_after_delete_denied",
    "other_tenant_survives_delete",
}


def external_output(root: Path, output: Path) -> Path:
    resolved = output.resolve()
    if resolved == root.resolve() or root.resolve() in resolved.parents:
        raise ValueError("acceptance_output_must_be_outside_source")
    return resolved


def git_identity(root: Path, expected_head: str) -> dict:
    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True, encoding="utf-8", timeout=15
        ).strip()

    head = git("rev-parse", "HEAD")
    if head != expected_head or not re.fullmatch(r"[a-f0-9]{40}", expected_head):
        raise RuntimeError("expected_head_mismatch")
    if git("status", "--porcelain"):
        raise RuntimeError("acceptance_requires_clean_source")
    return {"head": head, "tree": git("rev-parse", "HEAD^{tree}"), "clean": True}


def require_complete(report: dict, mode: str) -> None:
    if mode == "normal":
        if not report.get("actual_server_refresh_observed"):
            raise RuntimeError("actual_server_refresh_missing")
        required = REQUIRED_NORMAL
    else:
        required = {"auto_create_true_refreshed_rejoin_succeeds"}
    passed = {row.get("name") for row in report.get("cases", []) if row.get("passed") is True}
    if not required <= passed:
        raise RuntimeError("acceptance_cases_incomplete")


def server_config(key: str, secret: str, ports: tuple[int, int, int], auto_create: bool) -> dict:
    return {
        "port": ports[0],
        "bind_addresses": ["127.0.0.1"],
        "rtc": {
            "tcp_port": ports[1],
            "udp_port": ports[2],
            "use_external_ip": False,
            "enable_loopback_candidate": True,
        },
        "room": {"auto_create": auto_create},
        "keys": {key: secret},
        "logging": {"level": "warn"},
    }


def redact(value: str, known: list[str]) -> str:
    for secret in known:
        value = value.replace(secret, "[redacted]")
    return re.sub(
        r"[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}", "[redacted-jwt]", value
    )


def free_port(socktype=socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, socktype) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run(command: list[str], timeout: int, *, stdout=None):
    return subprocess.run(
        command,
        check=True,
        timeout=timeout,
        stdout=stdout,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = external_output(ROOT, args.output)
    output.mkdir(parents=True, exist_ok=True)
    source = git_identity(ROOT, args.expected_head)
    pin = json.loads((ROOT / "tests/acceptance/livekit/image.json").read_text(encoding="utf-8"))
    image = pin["repository"] + "@" + pin["digest"]
    if not re.fullmatch(r"livekit/livekit-server@sha256:[a-f0-9]{64}", image):
        raise RuntimeError("official_image_digest_required")
    run(["docker", "pull", image], 180, stdout=subprocess.DEVNULL)
    version = subprocess.check_output(
        ["docker", "run", "--rm", "--network", "none", image, "--version"],
        timeout=20,
        text=True,
        encoding="utf-8",
        stderr=subprocess.DEVNULL,
    ).strip()
    if not re.search(r"\b1\.13\.10\b", version):
        raise RuntimeError("sfu_version_mismatch")
    results = {
        "source": source,
        "image": pin,
        "server_version": version,
        "authority": "synthetic RS256 fixture only",
        "transport": "native RTC over loopback; no TURN acceptance",
        "runs": {},
    }
    # Keys, JWTs, raw server logs and the refresh handoff never enter artifact output.
    with tempfile.TemporaryDirectory(prefix="livekit-private-") as private_name:
        private = Path(private_name)
        key, secret = "acceptance-" + secrets.token_hex(8), secrets.token_hex(32)
        ports = (free_port(), free_port(), free_port(socket.SOCK_DGRAM))
        private_config = private / "client.json"
        private_config.write_text(
            json.dumps(
                {
                    "url": f"http://127.0.0.1:{ports[0]}",
                    "key": key,
                    "secret": secret,
                    "private": str(private),
                }
            ),
            encoding="utf-8",
        )
        for mode in ("normal", "mutation"):
            container = "livekit-admission-" + secrets.token_hex(8)
            config = private / "server.json"
            config.write_text(
                json.dumps(server_config(key, secret, ports, mode == "mutation")), encoding="utf-8"
            )
            try:
                run(
                    [
                        "docker",
                        "run",
                        "-d",
                        "--name",
                        container,
                        "--network",
                        "host",
                        "-v",
                        f"{config}:/etc/livekit.json:ro",
                        image,
                        "--config",
                        "/etc/livekit.json",
                    ],
                    45,
                    stdout=subprocess.DEVNULL,
                )
                deadline = time.monotonic() + 30
                while True:
                    try:
                        with urllib.request.urlopen(
                            f"http://127.0.0.1:{ports[0]}/", timeout=2
                        ) as r:
                            if r.status == 200:
                                break
                    except OSError:
                        pass
                    if time.monotonic() >= deadline:
                        raise RuntimeError("sfu_startup_timeout")
                    time.sleep(0.25)
                report_path = private / f"{mode}-receipt.json"
                protocol = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "tests/acceptance/livekit/live_protocol.py"),
                        "--mode",
                        mode,
                        "--config",
                        str(private_config),
                        "--receipt",
                        str(report_path),
                    ],
                    timeout=150,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                if protocol.returncode != 0:
                    diagnostic = re.search(
                        r"^Native SFU acceptance failed: ([A-Za-z0-9_]+)$",
                        protocol.stderr,
                        re.MULTILINE,
                    )
                    raise RuntimeError(
                        "protocol_" + (diagnostic.group(1) if diagnostic else "failed")
                    )
                report = json.loads(report_path.read_text(encoding="utf-8"))
                require_complete(report, mode)
                results["runs"][mode] = report
            finally:
                subprocess.run(
                    ["docker", "rm", "-f", container],
                    check=False,
                    timeout=20,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
    results["source_after"] = git_identity(ROOT, args.expected_head)
    body = json.dumps(results, indent=2, sort_keys=True) + "\n"
    safe = redact(body, [secret, key])
    if safe != body:
        raise RuntimeError("sensitive_receipt_rejected")
    (output / "admission-receipt.json").write_text(body, encoding="utf-8")
    (output / "admission-receipt.sha256").write_text(
        hashlib.sha256(body.encode()).hexdigest() + "\n", encoding="utf-8"
    )
    print("Actual pinned SFU admission and auto_create counterexample passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        # Never echo subprocess argv, server output, private paths or JWT exceptions.
        code = (
            str(exc)
            if isinstance(exc, RuntimeError) and re.fullmatch(r"[A-Za-z0-9_]+", str(exc))
            else type(exc).__name__
        )
        print(f"LiveKit acceptance failed: {code}", file=sys.stderr)
        raise SystemExit(1) from None
