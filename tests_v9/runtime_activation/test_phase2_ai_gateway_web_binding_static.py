from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_chatbot_uses_ai_agronomist_runtime_not_legacy_agent_or_mock_chat():
    src = read("frontend/src/sections/ChatbotPage.tsx")
    assert "kongApi.post('/api/ai-agronomist/chat'" in src
    assert "current_field_state" in src
    assert "activeFieldId" in src
    # سياق الحقل صار عبر hook `useSelectedField` + جلب `ai-context-pack` (بديل store مُفكَّك)؛
    # الحارس يتحقّق من الربط الفعليّ بسياق الحقل لا باسم store بائت.
    assert "useSelectedField" in src
    assert "ai-context-pack" in src
    assert "RAG/KG/FieldState" in src
    assert "kongApi.post('/api/agent/query'" not in src
    assert "'/api/chat'" not in src and '"/api/chat"' not in src


def test_ai_agronomist_exposes_phase2_e2e_routes_and_fetches_canonical_field_state():
    src = read("services/ai_agronomist/main.py")
    for route in [
        '@app.post("/v1/query")',
        '@app.post("/v1/chat")',
        '@app.post("/v1/explain")',
        '@app.post("/v1/recommend")',
    ]:
        assert route in src
    assert "/internal/fields/{field_id}/state" in src
    assert "X-Agent-Token" in src
    assert "RAG_BASE_URL" in src and "KNOWLEDGE_GRAPH_URL" in src and "PLATFORM_URL" in src
    assert "evidence_only" in src
    assert "field_intelligence_coordinator" in src
    assert "assert_no_decision_keys" in src


def test_gateway_routes_include_ai_runtime_rag_and_kg_with_auth_request():
    nginx = read("nginx/nginx.v9.conf")
    for block in [
        "location /api/rag/",
        "location /api/knowledge-graph/",
        "location /api/ai-agronomist/",
    ]:
        idx = nginx.index(block)
        snippet = nginx[idx : idx + 500]
        assert "auth_request /_auth_verify;" in snippet
        assert "proxy_set_header X-Tenant-Id $tenant;" in snippet
        assert "proxy_pass" in snippet


def test_compose_ai_runtime_has_strict_dependencies_and_agent_token():
    data = yaml.safe_load(read("docker-compose.v9.yml"))
    services = data["services"]
    ai = services["sahool-ai-agronomist"]
    assert ai["environment"]["RAG_BASE_URL"] == "http://sahool-rag-retrieval:8000"
    assert ai["environment"]["KNOWLEDGE_GRAPH_URL"] == "http://sahool-knowledge-graph:8000"
    assert ai["environment"]["PLATFORM_URL"] == "http://sahool-platform:8000"
    assert "SAHOOL_AGENT_TOKEN required" in ai["environment"]["SAHOOL_AGENT_TOKEN"]
    for dep in ["sahool-rag-retrieval", "sahool-knowledge-graph", "sahool-guardrails-engine"]:
        assert ai["depends_on"][dep]["condition"] == "service_healthy"
    assert "healthcheck" in ai


def test_vite_dev_proxy_preserves_gateway_paths_for_ai_runtime():
    src = read("frontend/vite.config.ts")
    assert "'/api'" in src
    assert "rewrite:" not in src.lower()
    assert "DEV_PROXY_TARGET" in src
