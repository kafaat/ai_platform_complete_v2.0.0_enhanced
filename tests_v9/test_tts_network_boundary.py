"""Real policy HTTP and Edge client with an audited, closed socket boundary.

The child process avoids global audit-hook and service-module contamination. No
provider or policy-fetch method is mocked. Only synthetic content is used. The
boundary permits the local policy server and rejects other Python socket/DNS
attempts before transmission. A valid-grant positive control must reach it.
This is local acceptance, not a Railway deployment or a kernel-wide egress proof.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
CASES = (
    "missing_origin",
    "missing_envelope",
    "old_version",
    "wrong_contract",
    "missing_contract",
    "tenant_mismatch",
    "llm_only",
    "explicit_denial",
    "unnamed_provider",
    "platform_down",
    "malformed_json",
    "local_only",
    "positive_control",
)


def _probe(case: str, endpoint: str) -> dict:
    import importlib.metadata
    import secrets
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    # A disposable test identity; no deployment secrets are read or emitted.
    os.environ["JWT_SECRET"] = secrets.token_hex(32)
    os.environ.pop("JWT_PUBLIC_KEY", None)
    os.environ["SAHOOL_ENV"] = "development"
    os.environ["XTTS_ENABLE"] = "0"
    os.environ["TTS_GPU_PROVIDER"] = ""
    os.environ["PIPER_VOICE_PATH"] = "/nonexistent-synthetic-probe-model.onnx"
    os.environ["TTS_EDGE_RETRY_ATTEMPTS"] = "1"
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "services/tts-service"))
    import jwt
    import main
    from fastapi.testclient import TestClient

    assert main._redis is None
    assert not any(p.available() for p in main._PROVIDER_REGISTRY if not p.external)
    assert any(p.available() for p in main._PROVIDER_REGISTRY if p.external)
    tenant = "00000000-0000-0000-0000-0000000000c7"
    token = jwt.encode(
        {"sub": "synthetic-probe", "iss": "sahool-auth", "aud": "sahool", "tenant_id": tenant},
        main.JWT_SECRET,
        algorithm="HS256",
    )
    envelope = {
        "contract": "sahool.ai_policy_envelope",
        "contract_version": 2,
        "tenant_id": tenant,
        "exp": int(time.time()) + 120,
        "policy_mode": "full_external",
        "external_tts_allowed": True,
        "external_tts_providers": ["edge_tts"],
        "external_llm_allowed": True,
    }
    payload = {"tenant_id": tenant, "ai_policy_envelope": envelope}
    if case == "missing_envelope":
        payload.pop("ai_policy_envelope")
    elif case == "old_version":
        envelope["contract_version"] = 1
    elif case == "wrong_contract":
        envelope["contract"] = "other.policy"
    elif case == "missing_contract":
        envelope.pop("contract")
    elif case == "tenant_mismatch":
        envelope["tenant_id"] = "other-tenant"
    elif case == "llm_only":
        envelope.pop("external_tts_allowed")
    elif case == "explicit_denial":
        envelope["external_tts_allowed"] = False
    elif case == "unnamed_provider":
        envelope["external_tts_providers"] = []
    elif case == "local_only":
        envelope["policy_mode"] = "local_only"
    policy_reads = []

    class PolicyHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == "/api/v1/me"
            assert self.headers["Authorization"] == f"Bearer {token}"
            policy_reads.append(True)
            body = b"not-json" if case == "malformed_json" else json.dumps(payload).encode()
            self.send_response(503 if case == "platform_down" else 200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), PolicyHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ["PLATFORM_API_URL"] = f"http://127.0.0.1:{port}"
    if case == "missing_origin":
        os.environ.pop("PLATFORM_API_URL")
    rejected_events = []
    allowed_connects = []

    def audit(event, args):
        if event == "socket.getaddrinfo":
            host, requested_port = args[:2]
            if host == "127.0.0.1" and requested_port == port:
                return
        elif event in {"socket.connect", "socket.sendto"}:
            address = args[1] if event == "socket.connect" else args[-1]
            if isinstance(address, tuple) and address[:2] == ("127.0.0.1", port):
                allowed_connects.append(event)
                return
        else:
            return
        # Do not emit destination addresses or authorization-bearing requests.
        rejected_events.append(event)
        raise PermissionError("synthetic acceptance egress boundary")

    sys.addaudithook(audit)
    try:
        client = TestClient(main.app, raise_server_exceptions=False)
        response = client.post(
            f"/v1/tts/{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "اختبار صوت اصطناعي", "voice": "yemeni_male"},
        )
        result = {
            "case": case,
            "endpoint": endpoint,
            "status": response.status_code,
            "policy_http_requests": len(policy_reads),
            "allowed_policy_connects": len(allowed_connects),
            "blocked_egress_attempts": len(rejected_events),
            "blocked_event_types": sorted(set(rejected_events)),
            "edge_tts_version": importlib.metadata.version("edge-tts"),
            "external_transmissions": 0,
        }
        if case == "positive_control":
            assert rejected_events, "Real Edge client did not reach the socket/DNS boundary"
        else:
            assert response.status_code == 503, result
            assert response.json()["detail"]["error"] == "local_provider_unavailable_for_policy"
            assert not rejected_events, result
        assert len(policy_reads) == (0 if case == "missing_origin" else 1), result
        return result
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("endpoint", ["synthesize", "stream"])
@pytest.mark.parametrize("case", CASES)
def test_actual_policy_http_and_edge_socket_boundary(case, endpoint):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--probe", case, endpoint],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout.split("BOUNDARY_RECEIPT=")[-1])
    print("BOUNDARY_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    assert receipt["case"] == case and receipt["endpoint"] == endpoint
    assert receipt["external_transmissions"] == 0


if __name__ == "__main__":
    assert len(sys.argv) == 4 and sys.argv[1] == "--probe"
    assert sys.argv[2] in CASES and sys.argv[3] in {"synthesize", "stream"}
    print("BOUNDARY_RECEIPT=" + json.dumps(_probe(sys.argv[2], sys.argv[3]), sort_keys=True))
