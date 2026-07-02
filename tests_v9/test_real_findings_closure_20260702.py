from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_ai_rejects_client_supplied_current_field_state_without_service_token():
    src = read("services/ai_agronomist/main.py")
    assert "current_field_state_requires_service_token" in src
    assert "service_token_ok(x_agent_token" in src
    assert "field_state = req.current_field_state" in src
    assert "_fetch_canonical_field_state" in src


def test_ai_forwards_trusted_tenant_to_kg_and_rag():
    src = read("services/ai_agronomist/main.py")
    assert 'headers={"X-Tenant-Id": tenant_id}' in src
    assert "resolve_trusted_tenant(x_tenant_id, req.tenant_id)" in src


def test_rag_ingest_is_internal_only_and_tenant_checked():
    src = read("services/rag-retrieval/main.py")
    assert "Depends(require_service_token)" in src
    assert "resolve_trusted_tenant(x_tenant_id, c.tenant_id)" in src
    assert "tenant_id = resolve_trusted_tenant(x_tenant_id, req.tenant_id)" in src


def test_knowledge_graph_reads_and_writes_have_internal_identity_guards():
    src = read("services/knowledge-graph/main.py")
    assert "Depends(require_service_token)" in src
    assert "Depends(require_trusted_tenant)" in src
    assert "async def edges(" in src
    assert "async def graphql(" in src


def test_v9_ai_uses_redis_backed_agent_store_by_default():
    data = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text())
    env = data["services"]["sahool-ai-agronomist"]["environment"]
    assert env["SAHOOL_AGENT_STORE_BACKEND"] == "${SAHOOL_AGENT_STORE_BACKEND:-redis}"
    assert "SAHOOL_AGENT_REDIS_URL" in env


def test_sam2_profile_has_default_inference_url_when_backend_enabled():
    data = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text())
    env = data["services"]["sahool-field-segmentation"]["environment"]
    assert env["SEGMENTATION_BACKEND"] == "${SEGMENTATION_BACKEND:-}"
    assert env["SEGMENTATION_INFERENCE_URL"].endswith("sahool-sam2-inference:8080/predict}")


def test_unified_and_light_edge_ports_match_internal_8100():
    for name in ["docker-compose.unified.yml", "docker-compose.light.yml"]:
        data = yaml.safe_load((ROOT / name).read_text())
        svc = data["services"]["edge-inference"]
        assert svc["ports"] == ["127.0.0.1:8100:8100"]
        assert "localhost:8100/healthz" in str(svc["healthcheck"]["test"])


def test_nginx_unified_upstreams_match_compose_service_names():
    src = read("nginx/nginx.unified.conf")
    for stale in [
        "sahool-auth:8000",
        "sahool-supervisor:8000",
        "sahool-frontend:80",
        "sahool-local-ai-rag:8000",
        "sahool-agriai-engine:8000",
    ]:
        assert stale not in src
    for expected in [
        "auth-service:8000",
        "supervisor-agent:8000",
        "frontend:80",
        "local-ai-rag:8000",
        "agriai-engine:8000",
        "erp-bridge:8126",
    ]:
        assert expected in src


def test_agent_store_fails_closed_in_production_when_redis_requested():
    src = read("services/ai_agronomist/agent_stores.py")
    assert "def _production_mode" in src
    assert "raise RuntimeError(msg)" in src
