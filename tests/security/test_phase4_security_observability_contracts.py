from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_committed_env_contains_only_placeholders() -> None:
    env_path = ".env" if (ROOT / ".env").exists() else ".env.example"
    env = read(env_path)
    forbidden_literals = [
        "UjUFyriLJw4bqDijpRWx5JmC3iqZzerA",
        "8143664452:",
        "i7R10UhllZ0zr67QfHJBB0PGL5kDnXfq",
        "1680da44e6499311fa3fd641f709b1bb485842c2fbe9e8e4dbaf05a977f4c34b",
        "Odoo@Sahool2026",
        "Sahool@" + "m6SDeVxyuqyE",
    ]
    for value in forbidden_literals:
        assert value not in env
    assert ("CHANGE_ME" in env) or ("change_me" in env) or ("CHANGE_THIS" in env)
    assert re.search(r"^DATABASE_URL=postgresql://sahool_app:", env, re.M)
    assert re.search(r"^JOBS_DATABASE_URL=postgresql://sahool_jobs:", env, re.M)


def test_security_audit_script_covers_secret_and_role_guards() -> None:
    src = read("scripts/security_audit.sh")
    assert src.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in src
    for needle in [
        "Telegram bot token",
        "CDSE client secret",
        "JWT secret",
        "service token",
        "POSTGRES_USER=postgres",
        "DATABASE_URL=.*(postgres|sahool_user)",
        "sslmode=disable",
    ]:
        assert needle in src


def test_ai_agronomist_fails_closed_for_missing_field_context_and_exposes_metrics() -> None:
    api_src = read("services/ai_agronomist/main.py")
    runtime_src = read("services/ai_agronomist/ai_evidence_runtime.py")
    assert '@app.get("/metrics")' in api_src
    assert "sahool_ai_agronomist_evidence_only 1" in api_src
    assert "field-specific advice fails closed" in runtime_src
    assert "canonical-field-state" in runtime_src
    assert 'field_state.get("status") in {"unavailable", "not_found"}' in runtime_src
    ast.parse(api_src)
    ast.parse(runtime_src)


def test_rag_and_knowledge_graph_have_readyz_and_metrics() -> None:
    for rel, metric in [
        ("services/rag-retrieval/main.py", "sahool_rag_retrieval_info"),
        ("services/knowledge-graph/main.py", "sahool_knowledge_graph_edges"),
    ]:
        src = read(rel)
        assert "readyz" in src
        assert "@app.get('/metrics')" in src or '@app.get("/metrics")' in src
        assert metric in src
        ast.parse(src)


def test_observability_and_outbox_scripts_exist() -> None:
    for rel in [
        "scripts/observability_smoke.sh",
        "scripts/outbox_reliability_check.sh",
    ]:
        src = read(rel)
        assert src.startswith("#!/usr/bin/env bash")
        assert "set -euo pipefail" in src
    obs = read("scripts/observability_smoke.sh")
    for path in [
        "/api/rag/readyz",
        "/api/knowledge-graph/readyz",
        "/api/ai-agronomist/readyz",
        "/api/ai-agronomist/metrics",
    ]:
        assert path in obs
    outbox = read("scripts/outbox_reliability_check.sh")
    assert "/api/v1/admin/outbox/dead-letter" in outbox
    assert "event_outbox" in outbox


def test_compose_uses_restricted_application_roles_and_ai_readiness() -> None:
    compose = read("docker-compose.v9.yml")
    assert "DATABASE_URL: ${DATABASE_URL:-postgresql://sahool_app:" in compose
    assert "JOBS_DATABASE_URL: ${JOBS_DATABASE_URL:-postgresql://sahool_jobs:" in compose
    assert "SAHOOL_AGENT_TOKEN: ${SAHOOL_AGENT_TOKEN:?SAHOOL_AGENT_TOKEN required}" in compose
    for service in ["sahool-rag-retrieval", "sahool-knowledge-graph", "sahool-ai-agronomist"]:
        assert re.search(rf"^\s{{2}}{service}:", compose, re.M), service
    # The service exposes /readyz at the gateway, while the container healthcheck
    # intentionally probes the lighter /healthz endpoint. Assert the actual
    # compose readiness dependency rather than a stale literal.
    assert "http://localhost:8000/healthz" in compose
    assert "sahool-ai-agronomist:" in compose
    assert "condition: service_healthy" in compose
