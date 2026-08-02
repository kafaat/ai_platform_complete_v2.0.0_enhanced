"""MCP protected body routes authenticate before request-body validation."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "services/mcp_servers"


def _load(name: str, path: Path):
    current = sys.modules.get(name)
    if current is not None:
        assert Path(getattr(current, "__file__", "")).resolve() == path.resolve()
        return current
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_missing_token_beats_malformed_body(monkeypatch: pytest.MonkeyPatch) -> None:
    _load("shared.oauth_middleware", MCP / "shared/oauth_middleware.py")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("MCP_SERVICE", "field")
    mod = _load("_mcp_auth_first_generic_context", MCP / "generic_context_server.py")
    client = TestClient(mod.app)
    response = client.post(
        "/v1/mcp/tools/call",
        content=b'{"name":',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 401, response.text


def test_missing_token_beats_schema_validation() -> None:
    mod = sys.modules["_mcp_auth_first_generic_context"]
    response = TestClient(mod.app).post("/v1/mcp/tools/call", json={})
    assert response.status_code == 401, response.text
