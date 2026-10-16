"""Real socket checks for the isolated reindex command's credential boundary."""

import importlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/sahool-platform"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/rag-retrieval"))
transport = importlib.import_module("runtime_transport")
pytestmark = pytest.mark.unit


def test_redirect_cannot_forward_api_key(monkeypatch):
    seen = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("api-key"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    target = ThreadingHTTPServer(("127.0.0.1", 0), Target)

    class Redirect(Target):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_port}/stolen")
            self.end_headers()

    source = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    servers = [source, target]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = transport.ReindexQdrantClient(
            f"http://127.0.0.1:{source.server_port}", "x", api_key="synthetic"
        )
        with pytest.raises(transport.QdrantHTTPError) as caught:
            client._request("GET", "/")
        assert caught.value.status == 302
        assert seen == []
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


def test_environment_proxy_is_not_installed(monkeypatch):
    monkeypatch.setenv("http_proxy", "http://invalid.example:8888")
    monkeypatch.setenv("https_proxy", "http://invalid.example:8888")
    client = transport.ReindexQdrantClient("https://internal.example", "x")
    import urllib.request

    assert not any(isinstance(h, urllib.request.ProxyHandler) for h in client._opener.handlers)


def test_response_size_is_bounded():
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, bound):
            return b"x" * bound

    class Opener:
        def open(self, *args, **kwargs):
            return Response()

    client = transport.ReindexQdrantClient("https://internal.example", "x")
    client._opener = Opener()
    client.max_response_bytes = 64
    with pytest.raises(ValueError, match="byte limit"):
        client._request("GET", "/")


def test_untagged_model_resolves_latest_and_requires_one_identity(monkeypatch):
    provider = transport.ReindexOllamaProvider("http://localhost:11434", "nomic-embed-text")
    monkeypatch.setattr(
        provider.client,
        "_request",
        lambda *a, **k: {"models": [{"name": "nomic-embed-text:latest", "digest": "a" * 64}]},
    )
    assert provider.model_digest() == "a" * 64
    monkeypatch.setattr(provider.client, "_request", lambda *a, **k: {"models": []})
    with pytest.raises(ValueError, match="identity unavailable"):
        provider.model_digest()
