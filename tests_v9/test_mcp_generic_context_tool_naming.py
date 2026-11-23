"""F9 — MCP tools named as search/get must say they only wrap what the caller sent.

``generic_context_server`` serves five deployed services whose tools perform **no**
retrieval: ``_rag`` returned the caller's own ``citations`` under the name
``search_rag_annotations`` and ``_kg`` the caller's own ``edges`` under
``query_kg_annotations``; the field/weather/lab/satellite tools likewise echoed the
caller's arguments under ``get_*`` names. A model reading the tool list would take
those answers as search/lookup results.

The contract below drives the real FastAPI app per ``MCP_SERVICE`` (the module reads
it at import, exactly as the container does) and requires that:

* every echo tool is listed under a name that says it wraps caller input, with a
  description that says no retrieval runs;
* every echo answer carries ``retrieval_performed: false`` and
  ``source: "caller_supplied"`` (RAG/KG stay reference context, never evidence);
* the old names still work as backward-compatible aliases, are reported as such in
  the answer, and are no longer advertised as tool names;
* the one tool that does read an owner (``iot`` → ``get_sensor_signal``) keeps its
  name and is not labelled as an echo.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "services/mcp_servers"
SECRET = "x" * 40
SCOPE = "mcp:context:read"

# service → (canonical tool name, deprecated alias, a caller-supplied argument set)
ECHO_TOOLS = {
    "rag": (
        "wrap_caller_rag_annotations",
        "search_rag_annotations",
        {"query": "salinity", "citations": [{"doc": "caller-doc", "score": 0.99}]},
    ),
    "knowledge-graph": (
        "wrap_caller_kg_annotations",
        "query_kg_annotations",
        {"subject": "wheat", "edges": [{"rel": "caller-edge", "object": "x"}]},
    ),
    "field": ("wrap_caller_field_context", "get_field_state", {"crop": "wheat"}),
    "weather": ("wrap_caller_weather_signal", "get_weather_signal", {"et0_mm": 5.0}),
    "lab": ("wrap_caller_lab_context", "get_lab_context", {"soil_ec": 2.1}),
    "satellite": (
        "wrap_caller_satellite_observation",
        "get_satellite_observation",
        {"ndvi": 0.7},
    ),
}

_SEARCH_VERBS = ("search", "query", "get_", "fetch", "lookup", "retrieve", "read_")


def _load_for(service: str, monkeypatch):
    import shared

    monkeypatch.setattr(shared, "__path__", [str(ROOT / "shared"), str(MCP / "shared")])
    monkeypatch.syspath_prepend(str(MCP))
    spec = importlib.util.spec_from_file_location(
        "_live_mcp_oauth", MCP / "shared/oauth_middleware.py"
    )
    if "_live_mcp_oauth" not in sys.modules:
        assert spec and spec.loader
        oauth = importlib.util.module_from_spec(spec)
        sys.modules["_live_mcp_oauth"] = oauth
        spec.loader.exec_module(oauth)
    monkeypatch.setitem(sys.modules, "shared.oauth_middleware", sys.modules["_live_mcp_oauth"])
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("SAHOOL_ALLOW_HS256_IN_PROD", raising=False)
    monkeypatch.setenv("MCP_SERVICE", service)
    name = "_f9_generic_context_" + service.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, MCP / "generic_context_server.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _headers(tenant: str = "tenant-a") -> dict:
    import jwt

    token = jwt.encode(
        {
            "sub": "42",
            "tenant_id": tenant,
            "scope": SCOPE,
            "iss": "sahool-auth",
            "aud": "sahool",
            "exp": int(time.time()) + 300,
        },
        SECRET,
        algorithm="HS256",
    )
    return {"Authorization": "Bearer " + token}


def _client(app):
    from fastapi.testclient import TestClient

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("service", sorted(ECHO_TOOLS))
def test_listed_echo_tool_name_and_description_say_no_retrieval(service, monkeypatch):
    canonical, alias, _ = ECHO_TOOLS[service]
    module = _load_for(service, monkeypatch)
    response = _client(module.app).get("/v1/mcp/tools", headers=_headers())
    assert response.status_code == 200, response.text
    tools = response.json()["tools"]
    names = [tool["name"] for tool in tools]
    assert names == [canonical], names
    assert alias not in names, "the misleading name must not be advertised as a tool"
    assert not canonical.startswith(_SEARCH_VERBS)
    (tool,) = tools
    description = tool["description"].lower()
    assert "caller" in description and "no retrieval" in description, description
    assert tool["retrieval_performed"] is False
    assert tool["deprecated_aliases"] == [alias]


@pytest.mark.parametrize("service", sorted(ECHO_TOOLS))
@pytest.mark.parametrize("use_alias", [False, True])
def test_echo_answer_declares_caller_supplied_and_no_retrieval(service, use_alias, monkeypatch):
    canonical, alias, arguments = ECHO_TOOLS[service]
    module = _load_for(service, monkeypatch)
    response = _client(module.app).post(
        "/v1/mcp/tools/call",
        json={"name": alias if use_alias else canonical, "arguments": arguments},
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieval_performed"] is False
    assert body["source"] == "caller_supplied"
    assert body["verified"] is False
    assert body["decision_authority"] == "none"
    assert body["tool"] == canonical
    assert body["deprecated_alias_used"] is use_alias
    # The values are exactly what the caller sent — nothing was looked up.
    for key, value in arguments.items():
        assert body["value"][key] == value


@pytest.mark.parametrize("service", ["rag", "knowledge-graph"])
def test_rag_kg_echo_stays_reference_context_not_evidence(service, monkeypatch):
    canonical, _, arguments = ECHO_TOOLS[service]
    module = _load_for(service, monkeypatch)
    body = (
        _client(module.app)
        .post(
            "/v1/mcp/tools/call",
            json={"name": canonical, "arguments": arguments},
            headers=_headers(),
        )
        .json()
    )
    assert body["type"] == "annotation"
    assert body["evidence_class"] == "reference_context"


def test_alias_of_another_service_is_not_accepted(monkeypatch):
    module = _load_for("rag", monkeypatch)
    response = _client(module.app).post(
        "/v1/mcp/tools/call",
        json={"name": "query_kg_annotations", "arguments": {}},
        headers=_headers(),
    )
    assert response.status_code == 404


def test_iot_tool_reads_an_owner_so_keeps_its_name(monkeypatch):
    module = _load_for("iot", monkeypatch)
    assert list(module.TOOLSETS["iot"]) == ["get_sensor_signal"]
    assert "iot" not in module.TOOL_ALIASES
    assert module.TOOL_RETRIEVAL["get_sensor_signal"] is True
