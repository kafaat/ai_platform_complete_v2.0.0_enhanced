from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
VLLM_DIGEST = "sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52"


def test_embedding_dimension_is_live_sourced_not_nominal_config():
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    overlay = (ROOT / "docker-compose.rag-kg-mcp.yml").read_text(encoding="utf-8")
    retrieval = (ROOT / "services/rag-retrieval/main.py").read_text(encoding="utf-8")
    contract = (ROOT / "docs/architecture/rag_embedding_contract.json").read_text(encoding="utf-8")
    assert "\nEMBEDDING_DIM=" not in "\n" + env
    assert "EMBEDDING_DIM:" not in overlay
    assert "vector_size=0" in retrieval
    assert '"dimension_source": "live_embedding_response"' in contract
    assert '"no_hardcoded_vector_dimension": true' in contract


def test_seed_vector_schema_mismatch_is_explicit_migration_requirement():
    source = (ROOT / "services/qdrant-seed/seed.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_collection_vector_size"
    )
    ns: dict[str, object] = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "seed_helper", "exec"), ns)
    info = SimpleNamespace(model_dump=lambda: {"config": {"params": {"vectors": {"size": 384}}}})
    assert ns["_collection_vector_size"](info) == 384
    assert "QDRANT_VECTOR_SCHEMA_MISMATCH" in source
    assert "refusing destructive auto-recreation" in source


def test_vllm_image_is_tag_and_digest_pinned_consistently():
    compose = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    expected = f"vllm/vllm-openai:v0.26.0@{VLLM_DIGEST}"
    assert expected in compose
    assert f"VLLM_IMAGE={expected}" in env


def test_inline_seed_provenance_is_not_forwarded_by_canonical_compose():
    compose = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
    section = compose.split("  sahool-qdrant-seed:", 1)[1].split("\n  sahool-", 1)[0]
    assert "QDRANT_SEED_PROVENANCE_FILE:" in section
    assert "QDRANT_SEED_PROVENANCE_JSON:" not in section
    assert "SAHOOL_ENV:" in section


def test_adapt_stays_deferred_by_repository_governance():
    decision = (ROOT / "services/sahool-platform/docs/REFERENCE_DOCS_CRITIQUE.md").read_text(
        encoding="utf-8"
    )
    assert "لا تبادل B2B لسهول" in decision
    assert not (ROOT / "shared/precision_agriculture/adapt_v2_edge.py").exists()
