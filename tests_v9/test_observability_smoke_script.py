"""``scripts/observability_smoke.sh`` must measure the endpoints it names.

The fault (audit F10): the script probed the gateway's guarded service aliases with no
``Authorization`` header, so against a working gateway every probe measured the identity
check (401), never the service; and any 2xx counted, including the SPA shell.

The script runs here against a loopback gateway stand-in that refuses without the fixture
token, exactly as ``auth_request`` does. No nginx; the gateway's own behaviour is proven in
``tests_v9/test_nginx_operational_aliases_contract.py`` and its runtime sibling.
"""

from __future__ import annotations

import http.server
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "observability_smoke.sh"
TOKEN = "fixture-valid-token"
READY = {
    "/readyz",
    "/api/raster/readyz",
    "/api/rag/readyz",
    "/api/knowledge-graph/readyz",
    "/api/ai-agronomist/readyz",
}
METRICS = {"/api/ai-agronomist/metrics", "/api/rag/metrics", "/api/knowledge-graph/metrics"}
GUARDED = (READY | METRICS) - {"/readyz"}
JSON = ("application/json", b'{"status":"ready"}')
PROMETHEUS = ("text/plain; version=0.0.4", b"# TYPE sahool_info gauge\nsahool_info 1\n")
SPA = ("text/html", b"<!doctype html><title>SAHOOL</title>")


class _Gateway(http.server.ThreadingHTTPServer):
    def __init__(self, override=None):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.override = override or {}
        self.seen: list[tuple[str, str | None]] = []


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        authorization = self.headers.get("Authorization")
        self.server.seen.append((self.path, authorization))
        if self.path in GUARDED and authorization != f"Bearer {TOKEN}":
            status, (content_type, body) = 401, ("application/json", b'{"detail":"unauthorized"}')
        elif self.path in self.server.override:
            status, (content_type, body) = self.server.override[self.path]
        elif self.path in READY:
            status, (content_type, body) = 200, JSON
        elif self.path in METRICS:
            status, (content_type, body) = 200, PROMETHEUS
        else:
            status, (content_type, body) = 404, ("application/json", b'{"detail":"Not Found"}')
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _run(token: str | None, override=None):
    assert shutil.which("curl"), "curl is required by the script under test"
    gateway = _Gateway(override)
    thread = threading.Thread(target=gateway.serve_forever, kwargs={"poll_interval": 0.05})
    thread.start()
    try:
        env = {k: v for k, v in os.environ.items() if k not in {"SAHOOL_JWT", "BASE_URL"}}
        env["BASE_URL"] = f"http://127.0.0.1:{gateway.server_port}/"
        if token is not None:
            env["SAHOOL_JWT"] = token
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
    finally:
        gateway.shutdown()
        gateway.server_close()
        thread.join(timeout=5)
    return result, gateway.seen


def test_every_probe_carries_the_token_and_all_eight_pass() -> None:
    result, seen = _run(TOKEN)
    assert result.returncode == 0, result.stdout + result.stderr
    assert {path for path, _ in seen} == READY | METRICS
    assert all(authorization == f"Bearer {TOKEN}" for _, authorization in seen), seen
    assert result.stdout.count("OK ") == 8, result.stdout
    assert TOKEN not in result.stdout + result.stderr


def test_without_a_token_it_refuses_before_probing() -> None:
    result, seen = _run(None)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "SAHOOL_JWT" in result.stderr
    assert not seen, f"probed without a token: {seen}"
    assert "OK " not in result.stdout


def test_a_blank_token_is_refused_too() -> None:
    result, seen = _run("")
    assert result.returncode == 2 and not seen, result.stdout + result.stderr


def test_a_rejected_token_fails_on_the_first_guarded_alias() -> None:
    result, _ = _run("not-the-token")
    assert result.returncode == 1
    assert "FAIL raster_ready" in result.stderr and "status=401" in result.stderr
    assert "not-the-token" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("path", "name", "answer"),
    [
        ("/api/rag/readyz", "rag_ready", (404, JSON)),
        ("/api/knowledge-graph/readyz", "kg_ready", (503, JSON)),
        ("/api/ai-agronomist/readyz", "ai_ready", (200, SPA)),
        ("/api/ai-agronomist/metrics", "ai_metrics", (200, SPA)),
        ("/api/rag/metrics", "rag_metrics", (200, JSON)),
        ("/api/knowledge-graph/metrics", "kg_metrics", (200, ("text/plain", b"ok\n"))),
    ],
)
def test_an_answer_that_is_not_the_named_endpoint_fails(path, name, answer) -> None:
    """A missing handler, a not-ready service, the SPA shell and a non-metrics body all fail."""
    result, _ = _run(TOKEN, {path: answer})
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"FAIL {name} " in result.stderr, result.stderr
    assert f"OK {name} " not in result.stdout
