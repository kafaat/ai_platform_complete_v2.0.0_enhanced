"""Run both baseline bootstrap and full shadow reindex against real local servers."""

import argparse
import asyncio
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import replace
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--runtime-root", type=Path, required=True)
parser.add_argument("--work-dir", type=Path, required=True)
args = parser.parse_args()
b = args.runtime_root.resolve()
repo = Path(__file__).resolve().parents[4]
out = Path(__file__).resolve().parent
sys.path.insert(0, str(repo / "services/sahool-platform"))
from core.rag.production_qdrant import (  # noqa: E402
    KnowledgeChunk,
    QdrantHttpClient,
)

sys.path.insert(0, str(repo / "services/rag-retrieval"))
from core.rag.production_qdrant import HybridQdrantRetriever  # noqa: E402
from reindex_manifest import ReindexSpec, inventory, prepare_shadow_reindex  # noqa: E402
from retrieval_profile import NOMIC_PROFILE, RetrievalProfile  # noqa: E402
from runtime_transport import ReindexOllamaProvider  # noqa: E402

work = Path(tempfile.mkdtemp(prefix="reindex-live-", dir=args.work_dir))
config = work / "qdrant.yaml"
config.write_text(
    "log_level: WARN\ntelemetry_disabled: true\nstorage:\n  storage_path: "
    + str(work / "storage")
    + "\nservice:\n  host: 127.0.0.1\n  http_port: 17333\n  grpc_port: 17334\n"
)
logs = [(work / "qdrant.log").open("w"), (work / "ollama.log").open("w")]
servers = [
    subprocess.Popen(
        [str(b / "rag-runtime-native/qdrant"), "--config-path", str(config)],
        cwd=work,
        stdout=logs[0],
        stderr=logs[0],
    ),
    subprocess.Popen(
        [str(b / "rag-ollama-runtime/bin/ollama"), "serve"],
        env={
            **os.environ,
            "OLLAMA_HOST": "127.0.0.1:11436",
            "OLLAMA_MODELS": str(b / "rag-ollama-runtime/models"),
            "OLLAMA_NO_CLOUD": "true",
        },
        stdout=logs[1],
        stderr=logs[1],
    ),
]
try:
    for url in ["http://127.0.0.1:17333/", "http://127.0.0.1:11436/api/tags"]:
        for _ in range(100):
            try:
                with urllib.request.urlopen(url, timeout=1) as r:
                    json.load(r)
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("native server unavailable")
    emb = ReindexOllamaProvider("http://127.0.0.1:11436", "nomic-embed-text:latest", timeout_s=60)
    chunks = [
        KnowledgeChunk(
            chunk_id=cid,
            tenant_id=tenant,
            text=text,
            source_type="uploaded_document",
            document_id=cid,
            chunk_index=0,
            total_chunks=1,
            metadata={
                "evidence_level": "document",
                "source_uri": "fixture://native-reindex",
                "source_revision": "original-v1",
            },
        )
        for cid, tenant, text in [
            ("uploaded-a", "tenant-a", "متابعة ري القمح من قياسات رطوبة التربة"),
            ("uploaded-b", "tenant-b", "متابعة نمو العنب وتقليم الأشجار"),
            ("seed:1", "__seed_quarantine__", "مرجع البذور المحجور ليس مصدراً حاكماً"),
        ]
    ]
    vectors = [emb.embed(c.text) for c in chunks]
    source = QdrantHttpClient("http://127.0.0.1:17333", "native_source")
    source.ensure_collection(vector_size=768)
    source.upsert(chunks, vectors)
    base = ReindexSpec(
        "native_source",
        "sahool_rag_reindex_native_v2",
        "candidate-v2",
        "0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f",
        "0" * 64,
        document_prefix="search_document: ",
        retrieval_profile=NOMIC_PROFILE,
    )
    original = inventory(source.scroll_payloads(), base)
    spec = replace(base, expected_source_payload_digest=original["payload_digest"])
    receipt = prepare_shadow_reindex(source, emb, spec)
    assert (
        receipt["source"]["tenants"]
        == receipt["candidate"]["tenants"]
        == {"tenant-a": 1, "tenant-b": 1, "__seed_quarantine__": 1}
    )
    assert (
        receipt["candidate"]["point_count"] == 3
        and receipt["source_preserved"]
        and not receipt["serving_authority_changed"]
    )
    candidate = QdrantHttpClient(source.base_url, spec.target_collection)
    rows = candidate.scroll_payloads()
    original_payloads = dict(source.scroll_payloads())
    for pid, payload in rows:
        expected = copy.deepcopy(original_payloads[pid])
        expected["metadata"].update(
            reindex_revision=spec.revision,
            embedding_model_digest=spec.model_digest,
            document_embedding_prefix=spec.document_prefix,
            retrieval_profile=spec.retrieval_profile,
        )
        assert payload == expected
    for tenant in ["tenant-a", "tenant-b"]:
        matches = candidate.search(emb.embed("search_query: ري القمح"), tenant_id=tenant, limit=10)
        assert len(matches) == 1 and all(
            p["metadata"]["tenant_id"] == tenant for _, _, p in matches
        )
    try:
        prepare_shadow_reindex(source, emb, spec)
    except ValueError as e:
        assert "candidate already exists" in str(e)
    else:
        raise AssertionError("existing candidate was overwritten")
    try:
        prepare_shadow_reindex(
            source,
            emb,
            replace(
                spec,
                target_collection="sahool_rag_reindex_stale",
                expected_source_payload_digest="f" * 64,
            ),
        )
    except ValueError as e:
        assert "differs" in str(e)
    else:
        raise AssertionError("stale inventory was accepted")
    assert source._request("GET", "/aliases")["result"]["aliases"] == []
    from dataclasses import asdict

    cli_spec = work / "operator-spec.json"
    cli_spec.write_text(
        json.dumps(
            {
                **asdict(replace(spec, target_collection="sahool_rag_reindex_operator_v2")),
                "model": "nomic-embed-text:latest",
            }
        )
    )
    cli_receipt = work / "operator-receipt.json"
    childenv = {
        **os.environ,
        "RAG_REINDEX_QDRANT_URL": source.base_url,
        "RAG_REINDEX_OLLAMA_URL": "http://127.0.0.1:11436",
    }
    subprocess.run(
        [
            sys.executable,
            str(repo / "services/qdrant-seed/reindex.py"),
            "--prepare-shadow",
            "--spec",
            str(cli_spec),
            "--output",
            str(cli_receipt),
        ],
        env=childenv,
        check=True,
    )
    cli_result = json.loads(cli_receipt.read_text())
    assert (
        cli_result["candidate"]["point_count"] == 3 and cli_receipt.stat().st_mode & 0o777 == 0o600
    )
    # Exercise the actual opt-in query profile against the real prepared vectors.
    serving = HybridQdrantRetriever(candidate, emb, retrieval_profile=RetrievalProfile(receipt))
    serving.rebuild_sparse_index()
    for tenant in ["tenant-a", "tenant-b"]:
        hits = serving.retrieve("ري القمح", tenant_id=tenant)
        assert hits and all(hit.chunk.tenant_id == tenant for hit in hits)
    # Mutate only stored vectors: payload-only checking would miss this drift.
    point_id = rows[0][0]
    candidate._request(
        "PUT",
        f"/collections/{candidate.collection}/points/vectors?wait=true",
        {"points": [{"id": point_id, "vector": [1.0] + [0.0] * 767}]},
    )
    try:
        serving.retrieve("ري القمح", tenant_id="tenant-a")
    except ValueError as exc:
        assert "vector inventory mismatch" in str(exc)
    else:
        raise AssertionError("vector-only drift was served")
    # Actual historical bootstrap behavior, in a different disposable collection.
    baseline = QdrantHttpClient(source.base_url, "native_baseline")
    baseline.ensure_collection(vector_size=768)
    baseline.upsert(chunks, vectors)
    os.environ.update(
        QDRANT_URL=source.base_url,
        COLLECTION_NAME="native_baseline",
        OLLAMA_BASE_URL="http://127.0.0.1:11436",
        EMBED_MODEL="nomic-embed-text:latest",
        QDRANT_SEED_REVISION="candidate-v2",
        QDRANT_SEED_TENANT_ID="__seed_quarantine__",
        SAHOOL_ENV="test",
    )
    old = work / "seed_baseline.py"
    old.write_bytes(
        subprocess.check_output(
            [
                "git",
                "show",
                "6e8cc0f9952c037550ae1644919f88c475dd89a7:services/qdrant-seed/seed.py",
            ],
            cwd=repo,
        )
    )
    sys.path.insert(0, str(repo / "services/qdrant-seed"))
    ms = importlib.util.spec_from_file_location("seed_baseline", old)
    seed = importlib.util.module_from_spec(ms)
    ms.loader.exec_module(seed)
    asyncio.run(seed.seed())
    baseline_rows = baseline.scroll_payloads()
    uploads = [
        p
        for _, p in baseline_rows
        if p.get("metadata", {}).get("chunk_id", "").startswith("uploaded-")
    ]
    result = {
        "base_sha": "6e8cc0f9952c037550ae1644919f88c475dd89a7",
        "runtimes": {"qdrant": "1.19.2", "ollama": "0.40.5", "model_digest": spec.model_digest},
        "baseline": {
            "operation": "actual main seed.seed() against disposable real Qdrant/Ollama",
            "original_points": 3,
            "result_points": len(baseline_rows),
            "uploaded_documents_reindexed": sum(
                p["metadata"].get("reindex_revision") == "candidate-v2" for p in uploads
            ),
            "full_reindex_contract_passed": False,
        },
        "candidate": receipt,
        "native_assertions": "Complete3point inventory, tenant and quarantine preservation, actual768dim document embeddings, source immutability, full candidate payload/vector verification, stale inventory rejected, existing target rejected, aliases unchanged",
        "versioned_profile_real_query_passed": True,
        "versioned_profile_vector_only_drift_rejected": True,
        "operator_cli_actual_run": True,
        "operator_receipt_mode": "0600",
        "production_touched": False,
        "logical_identity_migration_performed": False,
        "runtime_work_dir": str(work),
    }
    assert result["baseline"]["uploaded_documents_reindexed"] == 0 and len(baseline_rows) > 3
    (out / "native-profile-reindex-witness.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False), flush=True)
finally:
    for s in servers:
        s.terminate()
    for s in servers:
        s.wait(timeout=20)
    for f in logs:
        f.close()
