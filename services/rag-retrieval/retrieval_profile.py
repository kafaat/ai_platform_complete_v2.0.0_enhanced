"""Opt-in encoder/collection contract; no live cutover or default weight change.

The Nomic profile is development-validated on versioned Arabic seed passages.
Its weight was selected on the selection partition; the validation partition had
already been inspected during prefix diagnosis and is not an unseen holdout.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.rag.production_qdrant import RetrievalAdmissionError

LEGACY_PROFILE = "legacy-raw-v1"
NOMIC_PROFILE = "nomic-ar-seed-v1"
QUERY_PREFIX = "search_query: "
DENSE_WEIGHT = 0.1
SPARSE_WEIGHT = 0.9
NOMIC_DIGEST = "0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f"


@dataclass(frozen=True)
class RetrievalProfile:
    manifest: dict[str, Any]

    def __post_init__(self):
        m = self.manifest
        if (
            m.get("schema") != "sahool.rag-shadow-reindex/v1"
            or m.get("retrieval_profile") != NOMIC_PROFILE
            or m.get("model_digest") != NOMIC_DIGEST
            or m.get("document_prefix") != "search_document: "
            or m.get("query_prefix") != QUERY_PREFIX
            or m.get("dense_weight") != DENSE_WEIGHT
            or m.get("sparse_weight") != SPARSE_WEIGHT
            or m.get("vector_distance") != "Cosine"
            or m.get("vector_size") != 768
            or not re.fullmatch(
                r"sahool_rag_reindex_[a-zA-Z0-9_-]+", str(m.get("target_collection", ""))
            )
            or m.get("source_preserved") is not True
            or m.get("aliases_preserved") is not True
            or m.get("serving_authority_changed") is not False
            or not m.get("revision")
            or not isinstance(m.get("candidate"), dict)
            or not re.fullmatch(r"[0-9a-f]{64}", str(m["candidate"].get("payload_digest", "")))
            or type(m["candidate"].get("point_count")) is not int
            or not 1 <= m["candidate"]["point_count"] <= 100000
            or not re.fullmatch(r"[0-9a-f]{64}", str(m.get("candidate_vector_digest", "")))
        ):
            raise RetrievalAdmissionError("unqualified Nomic reindex manifest")
        # Detach from the caller's mutable receipt.
        object.__setattr__(self, "manifest", json.loads(json.dumps(m)))

    @classmethod
    def from_file(cls, path):
        with Path(path).open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise RetrievalAdmissionError("profile manifest exceeds byte limit")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise RetrievalAdmissionError("profile manifest must be an object")
        return cls(value)

    def validate_vectors(self, client):
        """Recheck the concrete collection; payload identity alone cannot bind vectors."""
        info = client._request("GET", f"/collections/{client.collection}")
        config = info.get("result", {}).get("config", {}).get("params", {}).get("vectors")
        if config != {"size": 768, "distance": "Cosine"}:
            # Qdrant may report optional vector settings; only the required settings
            # below are authoritative, and named vectors are never accepted.
            if (
                not isinstance(config, dict)
                or config.get("size") != 768
                or config.get("distance") != "Cosine"
            ):
                raise RetrievalAdmissionError("profile collection vector configuration mismatch")
        count = self.manifest["candidate"]["point_count"]
        observed = {}
        offset = None
        for _ in range(count // 128 + 2):
            body = {"limit": 128, "with_payload": False, "with_vector": True}
            if offset is not None:
                body["offset"] = offset
            result = client._request(
                "POST", f"/collections/{client.collection}/points/scroll", body
            )["result"]
            for row in result["points"]:
                point_id, vector = str(row["id"]), row["vector"]
                if (
                    point_id in observed
                    or not isinstance(vector, list)
                    or len(vector) != 768
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)
                ):
                    raise RetrievalAdmissionError("profile vector inventory malformed")
                observed[point_id] = vector
                if len(observed) > count:
                    raise RetrievalAdmissionError("profile vector count mismatch")
            offset = result.get("next_page_offset")
            if offset is None:
                break
        digest = hashlib.sha256(
            json.dumps(
                sorted(observed.items()), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        if (
            offset is not None
            or len(observed) != count
            or digest != self.manifest["candidate_vector_digest"]
        ):
            raise RetrievalAdmissionError("profile vector inventory mismatch")

    def validate_payload(self, payload):
        meta = payload.get("metadata", {})
        if (
            meta.get("reindex_revision") != self.manifest["revision"]
            or meta.get("embedding_model_digest") != NOMIC_DIGEST
            or meta.get("document_embedding_prefix") != "search_document: "
            or meta.get("retrieval_profile") != NOMIC_PROFILE
        ):
            raise RetrievalAdmissionError("payload encoding profile mismatch")

    def read_rows(self, client):
        count = self.manifest["candidate"]["point_count"]
        return client.scroll_payloads(page_size=128, max_pages=count // 128 + 2)

    def validate_rows(self, rows):
        for _, payload in rows:
            self.validate_payload(payload)
        digest = hashlib.sha256(
            json.dumps(
                sorted(rows, key=lambda r: r[0]),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if digest != self.manifest["candidate"]["payload_digest"] or len(rows) != self.manifest[
            "candidate"
        ].get("point_count"):
            raise RetrievalAdmissionError("profile collection inventory mismatch")

    def validate_encoder(self, client, embeddings):
        if client.collection != self.manifest["target_collection"]:
            raise RetrievalAdmissionError("profile collection mismatch")
        if getattr(embeddings, "model", "").split(":")[0] != "nomic-embed-text":
            raise RetrievalAdmissionError("profile requires the measured Nomic model")
        # Fresh model identity: an Ollama tag is mutable, so a configured name is insufficient.
        if embeddings.model_digest() != NOMIC_DIGEST:
            raise RetrievalAdmissionError("profile live model digest mismatch")
