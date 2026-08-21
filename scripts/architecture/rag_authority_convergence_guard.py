#!/usr/bin/env python3
"""ARCH-S3 Expand→Parity→Cutover→Revoke guard for RAG authority convergence."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "docs/architecture/rag_authority_convergence.json"
LOCAL = ROOT / "services/local-ai-rag/main.py"
LOCAL_REQ = ROOT / "services/local-ai-rag/requirements.txt"
RETRIEVAL = ROOT / "services/rag-retrieval/main.py"
EMBED_CONTRACT = ROOT / "docs/architecture/rag_embedding_contract.json"
COMPOSE = ROOT / "docker-compose.v9.yml"
RAG_OVERLAY = ROOT / "docker-compose.rag-kg-mcp.yml"
ENV_EXAMPLE = ROOT / ".env.example"
CATALOG = ROOT / "platform_catalog.generated.json"


def load() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8"))


def findings(state: dict | None = None, *, today: date | None = None) -> list[str]:
    state = state or load()
    today = today or date.today()
    out: list[str] = []
    # M0-C2: رُفِع إلى `/v2` حين انقسم `collection_schema_parity` اسمين في
    # `cutover_requirements`. ومفرداتُ الشرط جزءٌ من الشكل لا حاشيةٌ عليه: وثيقةٌ
    # بالمفردة القديمة تصف عقداً لم يعد قائماً، فتُرفَض هنا لا تُقرَأ قبولاً.
    #
    # وأوّلُ صياغةٍ للهجرة رفعت `version` وحده وأبقت `schema` على `/v1` — وهذا الحارس
    # **لا يقرأ `version` إطلاقاً**، فكان الإبطالُ مُعلَناً في نثرٍ ومفروضاً بلا شيء.
    # أمسكه مراجعٌ آليّ على #883.
    if state.get("schema") != "sahool.rag-authority-convergence/v2":
        return ["invalid schema"]
    if (
        state.get("intended_retrieval_authority") != "rag-retrieval"
        or state.get("generation_runtime") != "local-ai-rag"
    ):
        out.append("unexpected authority identities")
    local = LOCAL.read_text(encoding="utf-8")
    req = LOCAL_REQ.read_text(encoding="utf-8")
    retrieval = RETRIEVAL.read_text(encoding="utf-8")
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    env = compose["sahool-local-ai-rag"].get("environment") or {}
    if env.get("RAG_RETRIEVAL_URL") != "http://sahool-rag-retrieval:8000":
        out.append("local-ai-rag canonical retrieval URL not wired")
    if str(env.get("RAG_RETRIEVAL_SHADOW")) != "${RAG_RETRIEVAL_SHADOW:-false}":
        out.append("shadow must default false in EXPAND")
    if (
        "_shadow_canonical_retrieval" not in local
        or "RAG_RETRIEVAL_SHADOW_FAILED" not in local
        or "RAG_RETRIEVAL_SHADOW_PARITY" not in local
    ):
        out.append("shadow parity instrumentation missing")
    direct = (
        "QdrantVectorStore" in local
        or "qdrant_client" in local
        or "langchain-qdrant" in req
        or "qdrant-client" in req
    )
    contract = json.loads(EMBED_CONTRACT.read_text(encoding="utf-8"))
    if contract.get("schema") != "sahool.rag-embedding-contract/v1":
        out.append("invalid embedding contract schema")
    if (
        contract.get("dimension_source") != "live_embedding_response"
        or contract.get("no_hardcoded_vector_dimension") is not True
    ):
        out.append("embedding dimension contract must be live-response sourced and non-hardcoded")
    overlay = yaml.safe_load(RAG_OVERLAY.read_text(encoding="utf-8"))["services"]
    overlay_env = overlay["sahool-rag-retrieval"].get("environment") or {}
    if "EMBEDDING_DIM" in overlay_env:
        out.append("legacy RAG overlay hard-codes EMBEDDING_DIM")
    if re.search(r"(?m)^EMBEDDING_DIM=", ENV_EXAMPLE.read_text(encoding="utf-8")):
        out.append(".env.example hard-codes EMBEDDING_DIM")
    if "vector_size=0" not in retrieval:
        out.append("rag-retrieval must start with unknown Qdrant vector size and learn it live")
    provider_mismatch = (
        "HashEmbeddingProvider" in retrieval or "OllamaEmbeddingProvider" not in retrieval
    )
    reqs = state.get("cutover_requirements") or {}
    if provider_mismatch and reqs.get("embedding_contract_parity") is True:
        out.append("embedding parity claimed despite provider mismatch")
    if reqs.get("embedding_contract_parity") is True:
        if contract.get("provider") != "ollama" or contract.get("model") != "nomic-embed-text":
            out.append("embedding contract parity claimed against unexpected contract")
        if (
            env.get("EMBEDDING_MODEL") != "nomic-embed-text"
            or env.get("OLLAMA_BASE_URL") != "http://sahool-ollama:11434"
        ):
            out.append("rag-retrieval compose does not match embedding contract")
        local_env = compose["sahool-local-ai-rag"].get("environment") or {}
        if (
            local_env.get("EMBED_MODEL") != "nomic-embed-text"
            or local_env.get("OLLAMA_BASE_URL") != "http://sahool-ollama:11434"
        ):
            out.append("local-ai-rag compose does not match embedding contract")
    if reqs.get("canonical_ingest_parity") is True:
        if "vs.add_documents(chunks)" in local or "QdrantVectorStore.from_documents" in local:
            out.append("canonical ingest parity claimed while local direct Qdrant writer remains")
        if "RAG_RETRIEVAL_URL}/v1/ingest" not in local and "/v1/ingest" not in local:
            out.append("canonical ingest parity claimed without canonical ingest call")
    stage = state.get("stage")
    if stage in {"expand_shadow", "parity"}:
        if state.get("authority_state") != "NOT_YET_AUTHORITATIVE":
            out.append("pre-cutover stage must be NOT_YET_AUTHORITATIVE")
        exc = state.get("direct_qdrant_exception") or {}
        if not direct:
            out.append("EXPAND declaration stale: direct Qdrant already absent")
        for k in ("component_id", "owner", "reason", "target_close_by"):
            if not exc.get(k):
                out.append(f"direct Qdrant exception missing {k}")
        try:
            close = date.fromisoformat(str(exc.get("target_close_by")))
            if close < today:
                out.append("direct Qdrant exception expired")
        except ValueError:
            out.append("direct Qdrant exception target_close_by invalid")
        if any(bool(v) for v in reqs.values()) and not all(bool(v) for v in reqs.values()):
            # partial evidence is allowed, but authority must remain non-authoritative; no issue.
            pass
    elif stage in {"cutover", "revoked"}:
        if not all(bool(v) for v in reqs.values()):
            out.append("cutover/revoked stage without all cutover requirements")
        if direct:
            out.append("direct Qdrant remains after cutover")
        if "sahool-qdrant" in (compose["sahool-local-ai-rag"].get("depends_on") or {}):
            out.append("local-ai-rag still depends directly on Qdrant after cutover")
        if "RAG_RETRIEVAL_SHADOW" in local:
            out.append("shadow code remains after cutover instead of canonical primary")
    else:
        out.append(f"unknown stage {stage!r}")
    # Catalog must not prematurely claim rag-retrieval domain authority during EXPAND.
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    by = {c["component_id"]: c for c in cat["components"]}
    if (
        stage in {"expand_shadow", "parity"}
        and by["rag-retrieval"]["authority_kind"] == "domain_authority"
    ):
        out.append("catalog prematurely declares rag-retrieval authoritative")
    return out


def main() -> int:
    f = findings()
    if f:
        for x in f:
            print("rag_authority_convergence_fail", x)
        return 1
    s = load()
    blockers = len(s.get("blocking_reasons") or [])
    print(
        f"rag_authority_convergence_ok stage={s['stage']} "
        f"authority={s['authority_state']} blockers={blockers}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
