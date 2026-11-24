"""The W5 Arabic RAG baseline tool maps (tenant, chunk_id) to qrels, keeps its block reason
and never overwrites a report.

Defects found by the owner on ``4b476acb``:

1. the retriever caches chunks under ``chunk_identity`` = ``(tenant_id, chunk_id)``
   while the qrels are keyed ``seed:N``, so the tool rejected 32 of 32 queries as
   ``CURRENT_CORPUS_NEEDS_NEW_JUDGMENTS`` although ids and texts matched;
2. on failure the report kept only the exception class name;
3. the default ``--output`` was the historical ``baseline-results.json``.

No network: the real ``production_qdrant`` retriever, BM25 and chunk parsing run over an
in-memory Qdrant transport and a deterministic embedder. The tool's own read-only client
subclass still wraps that transport, so its mutation guard stays in the path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RAG = ROOT / "certification/evidence/chatgpt_w5_20261017/rag"
TOOL = RAG / "baseline_readonly.py"
SOURCE = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"
HISTORICAL = RAG / "baseline-results.json"
TENANT = "experiment-a"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def real_pq():
    return _load(SOURCE, "_w5_test_production_qdrant")


@pytest.fixture(scope="module")
def corpus():
    manifest = json.loads((RAG / "evaluation-v1.json").read_text(encoding="utf-8"))
    return json.loads((ROOT / manifest["corpus_path"]).read_text(encoding="utf-8"))["documents"]


def _chunk(pq, chunk_id, text, tenant=TENANT, **meta):
    metadata = {"evidence_level": "document", "source_class": "internal_document", **meta}
    return pq.KnowledgeChunk(
        chunk_id=chunk_id,
        tenant_id=tenant,
        text=text,
        source_type=metadata["source_class"],
        document_id=chunk_id,
        chunk_index=0,
        total_chunks=1,
        metadata=metadata,
    )


def _vector(text: str) -> list[float]:
    return [len(text) % 13 + 1.0, text.count("ا") + 1.0, text.count("ل") + 1.0]


class _Stack:
    """In-memory Qdrant and embedding service; records every request the tool sends."""

    def __init__(self, pq, chunks, embed_error=None, attempt_write=False):
        self.points = [(f"p-{n}", c.payload) for n, c in enumerate(chunks)]
        self.embed_error = embed_error
        self.attempt_write = attempt_write
        self.requests: list[tuple[str, str]] = []

    def fake_pq(self, pq):
        stack = self
        fake = types.ModuleType("w5_current_retriever")
        fake.__dict__.update({k: v for k, v in vars(pq).items() if not k.startswith("__")})

        class FakeQdrant(pq.QdrantHttpClient):
            def _request(self, method, path, payload=None):
                stack.requests.append((method, path))
                if path == "/":
                    return {"title": "fake qdrant"}
                if path == "/api/tags":
                    return {"models": [{"name": "nomic-embed-text:latest", "digest": "f" * 64}]}
                if path.endswith("/points/scroll"):
                    points = [{"id": i, "payload": p} for i, p in stack.points]
                    return {"result": {"points": points, "next_page_offset": None}}
                if path.endswith("/points/search"):
                    scope = set(payload["filter"]["must"][0]["match"]["any"])
                    rows = [
                        {
                            "id": i,
                            "score": sum(
                                a * b
                                for a, b in zip(
                                    payload["vector"], _vector(p["page_content"]), strict=True
                                )
                            ),
                            "payload": p,
                        }
                        for i, p in stack.points
                        if p["metadata"]["tenant_id"] in scope
                    ]
                    rows.sort(key=lambda r: (-r["score"], r["id"]))
                    return {"result": rows[: payload["limit"]]}
                raise AssertionError(f"unexpected request {method} {path}")

        class FakeEmbeddings(pq.OllamaEmbeddingProvider):
            def embed(self, text):
                stack.requests.append(("POST", "/api/embeddings"))
                if stack.embed_error is not None:
                    raise stack.embed_error
                return _vector(text)

        fake.QdrantHttpClient = FakeQdrant

        class FakeRetriever(pq.HybridQdrantRetriever):
            def rebuild_sparse_index(self):
                if stack.attempt_write:
                    self.qdrant._request("PUT", f"/collections/{self.qdrant.collection}/points")
                return super().rebuild_sparse_index()

        fake.OllamaEmbeddingProvider = FakeEmbeddings
        fake.HybridQdrantRetriever = FakeRetriever
        return fake


def _run(monkeypatch, tmp_path, pq, stack, output=None, tool_path=TOOL):
    tool = _load(tool_path, f"_w5_baseline_tool_{id(stack)}")
    real_load = tool.load
    fake = stack.fake_pq(pq)
    monkeypatch.setattr(
        tool,
        "load",
        lambda path, name: fake if name == "w5_current_retriever" else real_load(path, name),
    )
    output = output or tmp_path / "rerun.json"
    monkeypatch.setattr(sys, "argv", ["baseline_readonly.py", "--output", str(output)])
    code = tool.main()
    report = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
    return code, report


def _seed(pq, corpus):
    return [_chunk(pq, d["chunk_id"], d["text"]) for d in corpus]


def test_composite_identity_matches_qrels(monkeypatch, tmp_path, real_pq, corpus):
    stack = _Stack(real_pq, _seed(real_pq, corpus))
    code, report = _run(monkeypatch, tmp_path, real_pq, stack)
    assert report.get("runtime_blocker") is None, report.get("runtime_blocker_detail")
    assert code == 0 and report["status"] == "MEASURED"
    assert len(report["measurements"]) == 32
    for row in report["measurements"]:
        assert row["status"] == "MEASURED"
        final = row["stages"]["expansion_reranked"]
        assert final["metrics"] is not None
        assert all(i.startswith("seed:") for i in final["ids"])
    # Only reads, plus query embeddings: no Qdrant write was sent.
    assert {
        m
        for m, p in stack.requests
        if not p.endswith(("/points/scroll", "/points/search", "/api/embeddings"))
    } == {"GET"}


def test_other_tenants_chunks_never_count(monkeypatch, tmp_path, real_pq, corpus):
    own = _seed(real_pq, corpus)
    # Same logical ids under another tenant, with different text: if tenant were
    # dropped from the identity these would replace or join the evaluated chunks.
    other = [
        _chunk(real_pq, d["chunk_id"], "نص مستأجر آخر " + d["text"], tenant="experiment-b")
        for d in corpus
    ]
    stack = _Stack(real_pq, own + other)
    code, report = _run(monkeypatch, tmp_path, real_pq, stack)
    assert code == 0 and report["status"] == "MEASURED", report.get("runtime_blocker_detail")
    for row in report["measurements"]:
        for stage in row["stages"].values():
            assert {t for t, _ in stage["identities"]} <= {TENANT}


def test_eligible_global_chunk_blocks_instead_of_counting(monkeypatch, tmp_path, real_pq, corpus):
    reference = _chunk(
        real_pq,
        "seed:1",
        corpus[0]["text"],
        tenant=real_pq.GLOBAL_REFERENCE_TENANT,
        source_class="curated_reference",
        publisher="p",
        source_uri="https://example.invalid/r",
        source_revision="1",
        license="cc-by",
    )
    stack = _Stack(real_pq, _seed(real_pq, corpus) + [reference])
    code, report = _run(monkeypatch, tmp_path, real_pq, stack)
    assert code == 2 and report["status"] == "BLOCKED"
    assert "1 other-tenant visible" in report["runtime_blocker_detail"]


def test_foreign_result_is_not_graded(real_pq):
    tool = _load(TOOL, "_w5_baseline_tool_unit")
    metrics = _load(
        ROOT / "certification/evidence/chatgpt_closure_nine_20261016/rag/relevance_experiment.py",
        "_w5_test_metrics",
    ).metrics
    judgments = {"seed:1": 2, "seed:2": 0}
    foreign = _chunk(real_pq, "seed:1", "x", tenant="experiment-b")
    entry = tool.score_stage(metrics, [foreign], judgments, 1, TENANT)
    assert entry["metrics"] is None and entry["ids"] == ["foreign-tenant:experiment-b:seed:1"]
    own = tool.score_stage(metrics, [_chunk(real_pq, "seed:1", "x")], judgments, 1, TENANT)
    assert own["ids"] == ["seed:1"] and own["metrics"]["precision_at_k"] == 1.0


def test_block_reason_detail_is_kept_and_sanitized(monkeypatch, tmp_path, real_pq, corpus):
    error = ValueError(
        "embedding failed at http://admin:hunter2@127.0.0.1:11434/api/embeddings api_key=sk-123 "
        + "x" * 500
    )
    stack = _Stack(real_pq, _seed(real_pq, corpus), embed_error=error)
    code, report = _run(monkeypatch, tmp_path, real_pq, stack)
    assert code == 2 and report["runtime_blocker"] == "ValueError"
    detail = report["runtime_blocker_detail"]
    assert detail.startswith("embedding failed at http://[REDACTED]@127.0.0.1:11434")
    assert "hunter2" not in detail and "sk-123" not in detail and "admin" not in detail
    assert len(detail) <= 240


def test_existing_output_is_not_overwritten(monkeypatch, tmp_path, real_pq, corpus):
    existing = tmp_path / "earlier.json"
    existing.write_text('{"kept": true}\n', encoding="utf-8")
    stack = _Stack(real_pq, _seed(real_pq, corpus))
    code, _ = _run(monkeypatch, tmp_path, real_pq, stack, output=existing)
    assert code == 3
    assert existing.read_text(encoding="utf-8") == '{"kept": true}\n'
    assert stack.requests == []  # refused before any probe or embedding call


def test_output_is_required_and_history_untouched(monkeypatch):
    tool = _load(TOOL, "_w5_baseline_tool_args")
    with pytest.raises(SystemExit):
        tool.parse_args([])
    before = HISTORICAL.read_bytes()
    assert tool.main(["--output", str(HISTORICAL)]) == 3
    assert HISTORICAL.read_bytes() == before


def test_loopback_guard_remains():
    tool = _load(TOOL, "_w5_baseline_tool_guard")
    for url in ("http://10.0.0.5:6333", "https://127.0.0.1:6333", "http://u:p@127.0.0.1:6333"):
        with pytest.raises(ValueError):
            tool.loopback(url)
    assert tool.loopback("http://127.0.0.1:6333/") == "http://127.0.0.1:6333"


def test_qdrant_write_is_refused_before_it_is_sent(monkeypatch, tmp_path, real_pq, corpus):
    stack = _Stack(real_pq, _seed(real_pq, corpus), attempt_write=True)
    code, report = _run(monkeypatch, tmp_path, real_pq, stack)
    assert code == 2 and report["runtime_blocker"] == "RuntimeError"
    assert report["runtime_blocker_detail"] == "baseline prohibits remote mutations"
    assert all(method in {"GET", "POST"} for method, _ in stack.requests)


@pytest.mark.parametrize(
    "raw,leak",
    [
        ('payload {"api_key": "sk-json-1"}', "sk-json-1"),
        ("{'api_key': 'sk-repr-2'}", "sk-repr-2"),
        ('api_key="sk-quoted-3"', "sk-quoted-3"),
        ("https://x/?key=AIzaSECRET4", "AIzaSECRET4"),
        ("authorization=Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        ("Bearer abc.def.ghi failed", "abc.def.ghi"),
        ("postgres://user:p%40ss@h/db", "p%40ss"),
        ("http://u:" + "A" * 200 + "@h/x", "A" * 200),
        ("http://:onlypw@h/x", "onlypw"),
    ],
)
def test_sanitize_detail_redacts_quoted_and_scheme_secrets(raw, leak):
    tool = _load(TOOL, "_w5_baseline_tool_sanitize")
    assert leak not in tool.sanitize_detail(ValueError(raw))


def test_dangling_symlink_or_missing_directory_is_refused_before_any_request(
    monkeypatch, tmp_path, real_pq, corpus
):
    dangling = tmp_path / "dangling.json"
    dangling.symlink_to(tmp_path / "nowhere.json")
    stack = _Stack(real_pq, _seed(real_pq, corpus))
    code, _ = _run(monkeypatch, tmp_path, real_pq, stack, output=dangling)
    assert code == 3 and stack.requests == []
    code, _ = _run(monkeypatch, tmp_path, real_pq, stack, output=tmp_path / "no-dir" / "r.json")
    assert code == 3 and stack.requests == []


@pytest.mark.parametrize(
    "raw,kept",
    [
        ("http://127.0.0.1:6333 timed out; retry user@host", "timed out; retry user@host"),
        ("Index required for key: metadata.tenant_id", "metadata.tenant_id"),
        ("chunk key seed:1 missing", "seed:1"),
    ],
)
def test_sanitize_detail_keeps_ordinary_diagnostics(raw, kept):
    tool = _load(TOOL, "_w5_baseline_tool_keep")
    assert kept in tool.sanitize_detail(ValueError(raw))
