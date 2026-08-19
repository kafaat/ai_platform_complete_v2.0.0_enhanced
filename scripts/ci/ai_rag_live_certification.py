#!/usr/bin/env python3
"""Read-only live certification for SAHOOL's local AI/RAG runtime.

This probe validates the deployed chain without mutating production data:
  Ollama version/models/chat/embed
  -> Qdrant auth + vector schema
  -> canonical RAG readiness + tenant guards
  -> hybrid retrieval (dense and BM25 both contribute)
  -> AI Agronomist provider snapshot
  -> optional grounded chat proof when a canonical field/policy is supplied.

It never pulls models, ingests chunks, edits Qdrant, changes authority policy, or
executes tools.  A missing canonical field/policy for grounded generation is
EVIDENCE_REQUIRED, not a fabricated PASS.

Exit codes:
  0  PASS
  2  FAIL (runtime reached but a required invariant failed)
  3  EVIDENCE_REQUIRED (only optional/explicit live evidence is missing)
  4  HARNESS_INVALID / unreachable dependency
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

DEFAULT_OLLAMA_URL = "http://sahool-ollama:11434"
DEFAULT_QDRANT_URL = "http://sahool-qdrant:6333"
DEFAULT_RAG_URL = "http://sahool-rag-retrieval:8000"
DEFAULT_AI_URL = "http://sahool-ai-agronomist:8000"
DEFAULT_COLLECTION = "sahool_agri_kb"
DEFAULT_OLLAMA_VERSION = "0.32.5"
DEFAULT_CHAT_MODEL = "llama3.2:3b"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
GLOBAL_REFERENCE_TENANT = "__global__"
DEFAULT_HYBRID_QUERY = "القمح GDD النضج المناخ اليمني"


@dataclass
class Check:
    name: str
    status: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class HTTPResult:
    status: int
    body: dict[str, Any] | None
    text: str


def _request(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_s: float = 20.0,
) -> HTTPResult:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 - configured internal endpoints
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw else {}
            return HTTPResult(resp.status, parsed if isinstance(parsed, dict) else None, raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = None
        return HTTPResult(exc.code, parsed if isinstance(parsed, dict) else None, raw)


def _model_ids(payload: dict[str, Any] | None) -> list[str]:
    rows = (payload or {}).get("data")
    if not isinstance(rows, list):
        return []
    return sorted(str(row.get("id")) for row in rows if isinstance(row, dict) and row.get("id"))


def _canonical_model(value: str) -> str:
    value = (value or "").strip()
    return value[:-7] if value.endswith(":latest") else value


def _model_present(ids: list[str], expected: str) -> bool:
    target = _canonical_model(expected)
    return any(_canonical_model(x) == target for x in ids)


def _qdrant_vector_size(payload: dict[str, Any] | None) -> int | None:
    vectors = (
        (((payload or {}).get("result") or {}).get("config") or {}).get("params", {}).get("vectors")
    )
    if isinstance(vectors, dict) and isinstance(vectors.get("size"), int):
        return int(vectors["size"])
    return None


def _pass(name: str, detail: str, **evidence: Any) -> Check:
    return Check(name, "PASS", detail, evidence)


def _fail(name: str, detail: str, **evidence: Any) -> Check:
    return Check(name, "FAIL", detail, evidence)


def _evidence_required(name: str, detail: str, **evidence: Any) -> Check:
    return Check(name, "EVIDENCE_REQUIRED", detail, evidence)


def certify(
    *,
    tenant_id: str,
    field_id: str | None,
    crop: str | None,
    ollama_url: str,
    qdrant_url: str,
    rag_url: str,
    ai_url: str,
    collection: str,
    qdrant_api_key: str | None,
    expected_ollama_version: str,
    chat_model: str,
    embed_model: str,
    hybrid_query: str,
    require_generation: bool,
    timeout_s: float,
) -> dict[str, Any]:
    checks: list[Check] = []

    # Ollama: exact version and model inventory.
    version = _request("GET", f"{ollama_url.rstrip('/')}/api/version", timeout_s=timeout_s)
    if version.status != 200 or not version.body:
        raise RuntimeError(
            f"Ollama version endpoint unavailable: HTTP {version.status} {version.text[:160]}"
        )
    actual_version = str(version.body.get("version") or "")
    checks.append(
        _pass("ollama_version", actual_version, actual_version=actual_version)
        if actual_version == expected_ollama_version
        else _fail(
            "ollama_version",
            f"expected={expected_ollama_version} actual={actual_version or '<missing>'}",
            actual_version=actual_version,
        )
    )

    models = _request("GET", f"{ollama_url.rstrip('/')}/v1/models", timeout_s=timeout_s)
    if models.status != 200 or not models.body:
        raise RuntimeError(
            f"Ollama model endpoint unavailable: HTTP {models.status} {models.text[:160]}"
        )
    ids = _model_ids(models.body)
    checks.append(
        _pass("ollama_chat_model", chat_model, models=ids)
        if _model_present(ids, chat_model)
        else _fail("ollama_chat_model", f"missing {chat_model}", models=ids)
    )
    checks.append(
        _pass("ollama_embed_model", embed_model, models=ids)
        if _model_present(ids, embed_model)
        else _fail("ollama_embed_model", f"missing {embed_model}", models=ids)
    )

    embedding = _request(
        "POST",
        f"{ollama_url.rstrip('/')}/api/embeddings",
        payload={"model": embed_model, "prompt": "SAHOOL AI/RAG live certification"},
        timeout_s=timeout_s,
    )
    vec = (embedding.body or {}).get("embedding") if embedding.status == 200 else None
    if not isinstance(vec, list) or not vec or not all(isinstance(x, (int, float)) for x in vec):
        checks.append(
            _fail("ollama_embedding_smoke", f"HTTP {embedding.status}: invalid embedding")
        )
        embedding_dim = 0
    else:
        embedding_dim = len(vec)
        checks.append(
            _pass("ollama_embedding_smoke", f"dimensions={embedding_dim}", dimensions=embedding_dim)
        )

    chat = _request(
        "POST",
        f"{ollama_url.rstrip('/')}/v1/chat/completions",
        payload={
            "model": chat_model,
            "messages": [{"role": "user", "content": "Reply with exactly SAHOOL_OK"}],
            "temperature": 0,
            "max_tokens": 16,
            "stream": False,
        },
        timeout_s=timeout_s,
    )
    choices = (chat.body or {}).get("choices") if chat.status == 200 else None
    content = ""
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = str(message.get("content") or "").strip()
    checks.append(
        _pass("ollama_chat_smoke", content[:120], response_nonempty=True)
        if content
        else _fail("ollama_chat_smoke", f"HTTP {chat.status}: empty response")
    )

    # Qdrant must enforce the API key; missing/wrong credentials cannot look like an empty collection.
    collection_url = f"{qdrant_url.rstrip('/')}/collections/{collection}"
    if not qdrant_api_key:
        checks.append(
            _fail(
                "qdrant_api_key_configured", "QDRANT_API_KEY missing from certification environment"
            )
        )
        qdrant = None
    else:
        no_key = _request("GET", collection_url, timeout_s=timeout_s)
        checks.append(
            _pass("qdrant_rejects_missing_key", f"HTTP {no_key.status}")
            if no_key.status in {401, 403}
            else _fail("qdrant_rejects_missing_key", f"expected 401/403, got {no_key.status}")
        )
        bad_key = _request(
            "GET",
            collection_url,
            headers={"api-key": "sahool-invalid-cert-key"},
            timeout_s=timeout_s,
        )
        checks.append(
            _pass("qdrant_rejects_wrong_key", f"HTTP {bad_key.status}")
            if bad_key.status in {401, 403}
            else _fail("qdrant_rejects_wrong_key", f"expected 401/403, got {bad_key.status}")
        )
        qdrant = _request(
            "GET", collection_url, headers={"api-key": qdrant_api_key}, timeout_s=timeout_s
        )
        checks.append(
            _pass("qdrant_authenticated", f"HTTP {qdrant.status}")
            if qdrant.status == 200 and qdrant.body
            else _fail("qdrant_authenticated", f"HTTP {qdrant.status}: {qdrant.text[:160]}")
        )

    qdrant_dim = _qdrant_vector_size(qdrant.body if qdrant else None)
    checks.append(
        _pass("embedding_collection_dimension_parity", f"{embedding_dim}", vector_size=qdrant_dim)
        if embedding_dim > 0 and qdrant_dim == embedding_dim
        else _fail(
            "embedding_collection_dimension_parity",
            f"embedding={embedding_dim} qdrant={qdrant_dim}",
            embedding_dimensions=embedding_dim,
            qdrant_dimensions=qdrant_dim,
        )
    )

    # Canonical retrieval readiness must prove sparse reconstruction, not only HTTP liveness.
    ready = _request("GET", f"{rag_url.rstrip('/')}/readyz", timeout_s=timeout_s)
    r = ready.body or {}
    ready_ok = (
        ready.status == 200
        and r.get("status") == "ready"
        and r.get("embedding_contract_parity") is True
        and r.get("collection_schema_parity") is True
        and r.get("sparse_index_hydrated") is True
        and isinstance(r.get("sparse_index_count"), int)
        and int(r.get("sparse_index_count", 0)) > 0
    )
    checks.append(
        _pass(
            "rag_ready",
            f"sparse_index_count={r.get('sparse_index_count')}",
            sparse_index_count=r.get("sparse_index_count"),
            vector_size=r.get("vector_size"),
        )
        if ready_ok
        else _fail("rag_ready", f"HTTP {ready.status}: {ready.text[:300]}")
    )

    mismatch = _request(
        "POST",
        f"{rag_url.rstrip('/')}/v1/search",
        payload={"tenant_id": tenant_id + "-other", "query": hybrid_query, "final_k": 5},
        headers={"X-Tenant-Id": tenant_id},
        timeout_s=timeout_s,
    )
    checks.append(
        _pass("rag_tenant_mismatch_rejected", f"HTTP {mismatch.status}")
        if mismatch.status == 403
        else _fail("rag_tenant_mismatch_rejected", f"expected 403, got {mismatch.status}")
    )

    reserved = _request(
        "POST",
        f"{rag_url.rstrip('/')}/v1/search",
        payload={"tenant_id": GLOBAL_REFERENCE_TENANT, "query": hybrid_query, "final_k": 5},
        headers={"X-Tenant-Id": GLOBAL_REFERENCE_TENANT},
        timeout_s=timeout_s,
    )
    checks.append(
        _pass("rag_global_tenant_reserved", f"HTTP {reserved.status}")
        if reserved.status == 403
        else _fail("rag_global_tenant_reserved", f"expected 403, got {reserved.status}")
    )

    hybrid = _request(
        "POST",
        f"{rag_url.rstrip('/')}/v1/search",
        payload={"tenant_id": tenant_id, "query": hybrid_query, "final_k": 5},
        headers={"X-Tenant-Id": tenant_id},
        timeout_s=timeout_s,
    )
    annotations = (hybrid.body or {}).get("annotations") if hybrid.status == 200 else None
    rows = annotations if isinstance(annotations, list) else []
    hybrid_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        retr = row.get("retrieval")
        if not isinstance(retr, dict):
            continue
        dense = retr.get("dense_score")
        sparse = retr.get("bm25_score")
        if (
            isinstance(dense, (int, float))
            and isinstance(sparse, (int, float))
            and dense > 0
            and sparse > 0
        ):
            hybrid_rows.append(str(row.get("chunk_id") or ""))
    checks.append(
        _pass(
            "rag_hybrid_query",
            f"hits={len(rows)} hybrid_hits={len(hybrid_rows)}",
            hit_count=len(rows),
            hybrid_hit_count=len(hybrid_rows),
            hybrid_chunk_ids=hybrid_rows[:5],
        )
        if hybrid.status == 200 and rows and hybrid_rows
        else _fail(
            "rag_hybrid_query",
            f"HTTP {hybrid.status} hits={len(rows)} hybrid_hits={len(hybrid_rows)}",
            hit_count=len(rows),
            hybrid_hit_count=len(hybrid_rows),
        )
    )

    # Provider snapshot proves the AI Agronomist is actually bound to the upgraded local runtime.
    provider = _request("GET", f"{ai_url.rstrip('/')}/healthz/ai-provider", timeout_s=timeout_s)
    p = provider.body or {}
    provider_ok = (
        provider.status == 200
        and p.get("provider") == "local"
        and p.get("provider_class") == "local"
        and p.get("available") is True
        and p.get("model") == chat_model
        and p.get("wire_format") == "openai_chat"
    )
    checks.append(
        _pass(
            "ai_local_provider_binding",
            f"provider={p.get('provider')} model={p.get('model')}",
            generation_enabled=p.get("generation_enabled"),
            provider=p.get("provider"),
            model=p.get("model"),
            wire_format=p.get("wire_format"),
        )
        if provider_ok
        else _fail("ai_local_provider_binding", f"HTTP {provider.status}: {provider.text[:300]}")
    )

    # Optional end-to-end generation must use a real canonical field/policy. We do not inject a fake field state.
    if require_generation:
        if p.get("generation_enabled") is not True:
            checks.append(
                _evidence_required(
                    "grounded_generation",
                    "AI_GENERATION_ENABLED is false; enable explicitly for live grounded-generation certification",
                )
            )
        elif not field_id:
            checks.append(
                _evidence_required(
                    "grounded_generation",
                    "--field-id is required to prove generation against canonical field state/policy",
                )
            )
        else:
            generated = _request(
                "POST",
                f"{ai_url.rstrip('/')}/v1/chat",
                payload={
                    "tenant_id": tenant_id,
                    "field_id": field_id,
                    "crop": crop,
                    "question": hybrid_query,
                    "language": "ar",
                    "final_k": 5,
                },
                headers={"X-Tenant-Id": tenant_id},
                timeout_s=max(timeout_s, 60.0),
            )
            g = generated.body or {}
            gen_ok = (
                generated.status == 200
                and g.get("status") == "ok"
                and g.get("mode") == "generated_grounded"
                and g.get("generation_status") == "succeeded"
                and g.get("generation_provider") == "local"
                and g.get("generation_model") == chat_model
                and g.get("decision_authority") == "field_intelligence_coordinator"
                and ((g.get("guardrail_result") or {}).get("status") == "not_executed")
                and isinstance(((g.get("annotations") or {}).get("rag")), list)
                and bool((g.get("annotations") or {}).get("rag"))
            )
            checks.append(
                _pass(
                    "grounded_generation",
                    f"mode={g.get('mode')} evidence={len((g.get('annotations') or {}).get('rag') or [])}",
                    mode=g.get("mode"),
                    generation_status=g.get("generation_status"),
                    generation_provider=g.get("generation_provider"),
                    generation_model=g.get("generation_model"),
                )
                if gen_ok
                else _fail(
                    "grounded_generation",
                    f"HTTP {generated.status}: mode={g.get('mode')} status={g.get('generation_status')}",
                    response=g,
                )
            )

    statuses = {c.status for c in checks}
    status = (
        "FAIL"
        if "FAIL" in statuses
        else ("EVIDENCE_REQUIRED" if "EVIDENCE_REQUIRED" in statuses else "PASS")
    )
    return {
        "schema": "sahool.ai-rag-live-certification/v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "status": status,
        "read_only": True,
        "authority_promotion": False,
        "tenant_id": tenant_id,
        "field_id": field_id,
        "collection": collection,
        "expected_ollama_version": expected_ollama_version,
        "chat_model": chat_model,
        "embedding_model": embed_model,
        "checks": [asdict(c) for c in checks],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tenant-id", required=True)
    ap.add_argument("--field-id")
    ap.add_argument("--crop")
    ap.add_argument("--ollama-url", default=os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL))
    ap.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL))
    ap.add_argument("--rag-url", default=os.getenv("RAG_RETRIEVAL_URL", DEFAULT_RAG_URL))
    ap.add_argument("--ai-url", default=os.getenv("AI_AGRONOMIST_URL", DEFAULT_AI_URL))
    ap.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", DEFAULT_COLLECTION))
    ap.add_argument("--expected-ollama-version", default=DEFAULT_OLLAMA_VERSION)
    ap.add_argument("--chat-model", default=os.getenv("LOCAL_LLM_MODEL", DEFAULT_CHAT_MODEL))
    ap.add_argument("--embed-model", default=os.getenv("EMBEDDING_MODEL", DEFAULT_EMBED_MODEL))
    ap.add_argument("--hybrid-query", default=DEFAULT_HYBRID_QUERY)
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--require-generation", action="store_true")
    ap.add_argument("--out", default="-")
    args = ap.parse_args(argv)

    try:
        result = certify(
            tenant_id=args.tenant_id,
            field_id=args.field_id,
            crop=args.crop,
            ollama_url=args.ollama_url,
            qdrant_url=args.qdrant_url,
            rag_url=args.rag_url,
            ai_url=args.ai_url,
            collection=args.collection,
            qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
            expected_ollama_version=args.expected_ollama_version,
            chat_model=args.chat_model,
            embed_model=args.embed_model,
            hybrid_query=args.hybrid_query,
            require_generation=args.require_generation,
            timeout_s=args.timeout,
        )
    except (
        urllib.error.URLError,
        TimeoutError,
        ConnectionError,
        RuntimeError,
        json.JSONDecodeError,
    ) as exc:
        result = {
            "schema": "sahool.ai-rag-live-certification/v1",
            "observed_at": datetime.now(UTC).isoformat(),
            "status": "HARNESS_INVALID",
            "read_only": True,
            "authority_promotion": False,
            "error": str(exc),
        }

    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out == "-":
        print(rendered, end="")
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(rendered)
        print(f"ai_rag_live_certification_written status={result['status']} out={args.out}")

    return {"PASS": 0, "FAIL": 2, "EVIDENCE_REQUIRED": 3, "HARNESS_INVALID": 4}.get(
        result.get("status"), 4
    )


if __name__ == "__main__":
    sys.exit(main())
