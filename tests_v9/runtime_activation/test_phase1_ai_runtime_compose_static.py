from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def test_phase1_ai_runtime_services_are_in_canonical_compose():
    data = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    services = data["services"]
    for name in ["sahool-rag-retrieval", "sahool-knowledge-graph", "sahool-ai-agronomist"]:
        assert name in services
        assert "healthcheck" in services[name]
        assert services[name]["restart"] == "unless-stopped"
        assert "sahool-internal" in services[name]["networks"]
    assert (
        services["sahool-ai-agronomist"]["depends_on"]["sahool-rag-retrieval"]["condition"]
        == "service_healthy"
    )
    assert (
        services["sahool-ai-agronomist"]["depends_on"]["sahool-knowledge-graph"]["condition"]
        == "service_healthy"
    )


def test_phase1_gateway_routes_are_present():
    nginx = (ROOT / "nginx/nginx.v9.conf").read_text(encoding="utf-8")
    for token in [
        "upstream rag_backend",
        "upstream kg_backend",
        "upstream ai_agronomist_backend",
        "location /api/rag/",
        "location /api/knowledge-graph/",
        "location /api/ai-agronomist/",
    ]:
        assert token in nginx


def test_workers_have_readiness_healthchecks():
    data = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    for name in ["sahool-weather-polygon-worker", "sahool-weather-signal-engine"]:
        service = data["services"][name]
        assert "healthcheck" in service
        assert "/app/worker_health_probe.py" in " ".join(service["healthcheck"]["test"])
