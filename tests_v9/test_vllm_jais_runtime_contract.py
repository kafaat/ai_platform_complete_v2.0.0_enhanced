from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
MODEL_REPO = "Solshine/Jais-adapted-7B-Reflection-Tuning-Natural-Farmer"


def _compose():
    return yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_vllm_service_is_internal_opt_in_infrastructure():
    svc = _compose()["services"]["sahool-vllm-jais"]
    assert svc["image"].startswith("${VLLM_IMAGE:-vllm/vllm-openai:")
    assert "vllm" in svc.get("profiles", [])
    assert "ports" not in svc
    assert "QDRANT_URL" not in svc.get("environment", {})
    assert "sahool-qdrant" not in (svc.get("depends_on") or {})
    command = [str(v) for v in svc["command"]]
    assert any(MODEL_REPO in v for v in command)
    assert "${VLLM_MODEL:-jais-natural-farmer}" in command
    assert "/health" in svc["healthcheck"]["test"][-1]


def test_vllm_wired_only_to_generation_boundaries_not_legacy_qdrant_rag():
    services = _compose()["services"]
    for name in ("sahool-platform", "sahool-ai-agronomist"):
        env = services[name]["environment"]
        assert env["AI_PROVIDER"] == "${AI_PROVIDER:-local}"
        assert env["VLLM_BASE_URL"] == "${VLLM_BASE_URL:-http://sahool-vllm-jais:8000/v1}"
        assert env["VLLM_MODEL"] == "${VLLM_MODEL:-jais-natural-farmer}"
    # Deliberate: do not attach Jais/vLLM to the legacy local-ai-rag process that can
    # still see Qdrant before S3 authority cutover.
    legacy_env = services["sahool-local-ai-rag"]["environment"]
    assert "VLLM_BASE_URL" not in legacy_env
    assert "VLLM_MODEL" not in legacy_env


def test_generation_adapter_is_openai_compatible_and_tools_default_off(monkeypatch):
    gen = _load("services/ai_agronomist/ai_generation.py", "vllm_generation_under_test")
    monkeypatch.setenv("AI_PROVIDER", "vllm")
    monkeypatch.delenv("VLLM_ENABLE_TOOLS", raising=False)
    cfg = gen.resolve_generation()
    assert cfg is not None
    assert cfg.provider == "vllm"
    assert cfg.wire_format == "openai_chat"
    assert cfg.endpoint.endswith("/v1/chat/completions")
    assert gen._provider_tools(cfg, ["anything"]) == []


def test_env_default_remains_local_and_exact_vllm_switch_is_documented():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "AI_PROVIDER=local" in example
    assert "VLLM_MODEL_REPOSITORY=" + MODEL_REPO in example
    assert "AI_PROVIDER=vllm" in example


def test_model_runtime_contract_declares_no_domain_or_retrieval_authority():
    contract = json.loads((ROOT / "config/ai-model-runtimes/jais-natural-farmer.json").read_text())
    assert contract["provider"] == "vllm"
    assert contract["model_repository"] == MODEL_REPO
    assert contract["domain_authority"] is False
    assert contract["authority_kind"] == "infrastructure"
    assert contract["retrieval_authority"] == "rag-retrieval"
    assert contract["direct_vector_store_access"] is False


def test_runtime_registered_as_infrastructure_only():
    registry = json.loads((ROOT / "docs/architecture/component_registry.json").read_text())
    assert "sahool-vllm-jais" in registry["infrastructure_units"]
    assert "vllm-jais" not in registry["components"]
