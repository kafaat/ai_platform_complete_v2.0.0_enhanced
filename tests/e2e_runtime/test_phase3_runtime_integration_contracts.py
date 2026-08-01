from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_gateway_routes_cover_runtime_services() -> None:
    nginx = read("nginx/nginx.v9.conf")
    compose = read("docker-compose.v9.yml")
    for route in [
        "/api/raster/",
        "/api/v1/",
        "/api/rag/",
        "/api/knowledge-graph/",
        "/api/ai-agronomist/",
        "/api/guardrails/",
        "/api/soil/",
    ]:
        assert f"location {route}" in nginx or f"location = {route.rstrip('/')}" in nginx
    for service in [
        "sahool-platform",
        "sahool-raster-service",
        "sahool-rag-retrieval",
        "sahool-knowledge-graph",
        "sahool-ai-agronomist",
        "sahool-guardrails-engine",
    ]:
        assert re.search(rf"^\s{{2}}{re.escape(service)}:", compose, re.M), service


def test_ai_agronomist_is_evidence_only_and_audited() -> None:
    api_src = read("services/ai_agronomist/main.py")
    runtime_src = read("services/ai_agronomist/ai_evidence_runtime.py")
    assert "/internal/fields/{field_id}/state" in runtime_src
    assert "/internal/events/ai-advice" in runtime_src
    assert "_record_ai_advice_event" in runtime_src
    assert "evidence_only" in api_src
    assert "field_intelligence_coordinator" in runtime_src
    forbidden_payload_keys = ["'recommendations'", '"recommendations"', "'tasks'", '"tasks"']
    for bad in forbidden_payload_keys:
        assert bad not in runtime_src


def test_platform_has_internal_ai_advice_event_endpoint() -> None:
    src = read("services/sahool-platform/api/routers/internal_service.py")
    assert '@router.post("/internal/events/ai-advice")' in src
    assert "AI_SUGGESTION" in src
    assert "_require_service_token" in src
    assert "tenant_connection_for" in src


def test_runtime_scripts_are_present_and_safe() -> None:
    for rel in [
        "scripts/check_gateway_routes.sh",
        "scripts/runtime_smoke.sh",
        "scripts/e2e/e2e_field_imagery_ai.sh",
    ]:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env bash")
        assert "set -euo pipefail" in text
    e2e = read("scripts/e2e/e2e_field_imagery_ai.sh")
    assert "SAHOOL_JWT" in e2e
    assert "tilejson" in e2e
    assert "api/ai-agronomist/chat" in e2e


def test_python_files_parse_for_phase3_touched_files() -> None:
    for rel in [
        "services/ai_agronomist/main.py",
        "services/sahool-platform/api/main.py",
    ]:
        ast.parse(read(rel), filename=rel)
