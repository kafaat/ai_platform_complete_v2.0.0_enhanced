"""The compose knowledge-graph container must receive the service token Helm gives it.

The fault (audit F10): ``POST /v1/nodes`` and ``POST /v1/edges`` depend on
``require_service_token``, which reads ``SAHOOL_AGENT_TOKEN`` at request time and refuses
every caller when it is blank. ``helm/sahool/values.yaml`` passes the secret to
``sahool-knowledge-graph``; the same block in ``docker-compose.v9.yml`` did not, so on
compose every graph write answered 403 whatever the caller sent.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

from shared.security.gateway_deps import require_service_token

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
KG = "sahool-knowledge-graph"
REQUIRED = "${SAHOOL_AGENT_TOKEN:?SAHOOL_AGENT_TOKEN required}"


def _compose_environment(service: str) -> dict[str, str]:
    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    return compose["services"][service].get("environment") or {}


def test_helm_passes_the_service_token_to_the_knowledge_graph() -> None:
    values = yaml.safe_load((ROOT / "helm/sahool/values.yaml").read_text(encoding="utf-8"))
    assert values["workloads"][KG]["secretEnv"]["SAHOOL_AGENT_TOKEN"] == "agentToken"


def test_compose_passes_the_service_token_to_the_knowledge_graph() -> None:
    assert _compose_environment(KG).get("SAHOOL_AGENT_TOKEN") == REQUIRED, (
        f"{KG} gets no SAHOOL_AGENT_TOKEN on compose: every graph write answers 403"
    )


def test_it_is_passed_the_way_the_sibling_services_pass_it() -> None:
    """Required, never defaulted: a blank token must stop `compose up`, not open or close writes."""
    for sibling in ("sahool-rag-retrieval", "sahool-ai-agronomist"):
        assert _compose_environment(sibling)["SAHOOL_AGENT_TOKEN"] == REQUIRED
    assert ":-" not in _compose_environment(KG).get("SAHOOL_AGENT_TOKEN", ":-")


def test_the_graph_writes_depend_on_that_token() -> None:
    source = (ROOT / "services/knowledge-graph/main.py").read_text(encoding="utf-8")
    for route in ('@app.post("/v1/nodes")', '@app.post("/v1/edges")'):
        declaration = source[source.index(route) :].split("\n", 2)[1]
        assert "Depends(require_service_token)" in declaration, route


def test_a_container_without_the_token_refuses_every_writer(monkeypatch) -> None:
    monkeypatch.delenv("SAHOOL_AGENT_TOKEN", raising=False)
    for sent in (None, "", "any-value"):
        with pytest.raises(HTTPException) as refused:
            require_service_token(sent)
        assert refused.value.status_code == 403


def test_with_the_token_only_the_matching_caller_writes(monkeypatch) -> None:
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "fixture-service-token")
    assert require_service_token("fixture-service-token") is None
    for sent in (None, "", "wrong-token"):
        with pytest.raises(HTTPException) as refused:
            require_service_token(sent)
        assert refused.value.status_code == 403
