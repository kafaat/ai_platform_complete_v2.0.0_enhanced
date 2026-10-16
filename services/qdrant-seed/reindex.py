"""Explicit full-corpus shadow reindex; never a production reseed or alias cutover."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sahool-platform"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rag-retrieval"))

from reindex_manifest import ReindexSpec, inventory, prepare_shadow_reindex  # noqa: E402
from runtime_transport import (  # noqa: E402
    ReindexOllamaProvider,
    ReindexQdrantClient,
    origin,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--prepare-shadow", action="store_true")
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.spec.read_text(encoding="utf-8"))
    model = data.pop("model")
    if ":" not in model:
        model += ":latest"
    spec = ReindexSpec(**data)
    # Reserve the private receipt before any remote operation or candidate write.
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(
            {"status": "STARTED_NOT_ACCEPTED", "target_collection": spec.target_collection}, stream
        )
        stream.flush()
        os.fsync(stream.fileno())
        source = ReindexQdrantClient(
            origin(os.environ["RAG_REINDEX_QDRANT_URL"]),
            spec.source_collection,
            api_key=os.getenv("RAG_REINDEX_QDRANT_API_KEY") or None,
        )
        if args.inspect:
            rows = source.scroll_payloads(
                page_size=min(spec.max_points + 1, 256), max_pages=spec.max_points // 256 + 2
            )
            result = inventory(rows, spec)
            if source.collection_point_count() != result["point_count"]:
                raise ValueError("incomplete inventory")
            result["read_only"] = True
        else:
            ollama = origin(os.environ["RAG_REINDEX_OLLAMA_URL"])
            models = ReindexQdrantClient(ollama, "unused")

            def verify_model() -> None:
                entries = models._request("GET", "/api/tags")["models"]
                selected = [m for m in entries if m.get("name") == model or m.get("model") == model]
                if len(selected) != 1 or selected[0].get("digest") != spec.model_digest:
                    raise ValueError("live model digest differs from the reviewed specification")
                if spec.document_prefix and model.split(":")[0] != "nomic-embed-text":
                    raise ValueError("Nomic document prefix requested for another model")

            verify_model()
            result = prepare_shadow_reindex(
                source,
                ReindexOllamaProvider(ollama, model),
                spec,
                client_factory=ReindexQdrantClient,
            )
            verify_model()
        # Payload inventories may contain tenant identifiers. New evidence is private.
        stream.seek(0)
        stream.truncate()
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


if __name__ == "__main__":
    main()
