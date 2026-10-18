"""Bounded direct transport used only by the explicit shadow-reindex command."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from core.rag.production_qdrant import OllamaEmbeddingProvider, QdrantHttpClient, QdrantHTTPError


class RetrievalDependencyError(ValueError):
    """Known malformed or inadmissible upstream response."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("HTTP origin without embedded credentials required")
    return value.rstrip("/")


class ReindexQdrantClient(QdrantHttpClient):
    """Never forwards credentials through environment proxies or HTTP redirects."""

    max_response_bytes = 32 * 1024 * 1024

    def __init__(self, base_url, collection, **kwargs):
        super().__init__(origin(base_url), collection, **kwargs)
        if not 0 < self.timeout_s <= 60:
            raise ValueError("bounded request timeout required")
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def _request(self, method, path, payload=None):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("same-origin absolute path required")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        req = urllib.request.Request(
            self.base_url + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers=headers,
            method=method,
        )
        try:
            with self._opener.open(req, timeout=self.timeout_s) as response:
                raw = response.read(self.max_response_bytes + 1)
                if len(raw) > self.max_response_bytes:
                    raise RetrievalDependencyError("reindex response exceeds byte limit")
                result = json.loads(raw) if raw else {}
                if not isinstance(result, dict):
                    raise RetrievalDependencyError("reindex response must be a JSON object")
                return result
        except json.JSONDecodeError:
            raise RetrievalDependencyError("upstream response is not JSON") from None
        except urllib.error.HTTPError as exc:
            # Do not echo provider bodies, redirect targets, or credentials.
            exc.close()
            raise QdrantHTTPError(exc.code, "reindex HTTP request refused") from None


class ReindexOllamaProvider(OllamaEmbeddingProvider):
    def __init__(self, base_url, model, timeout_s=20.0):
        super().__init__(origin(base_url), model, timeout_s)
        self.client = ReindexQdrantClient(base_url, "unused", timeout_s=timeout_s)

    def model_digest(self):
        model = self.model if ":" in self.model else self.model + ":latest"
        tags = self.client._request("GET", "/api/tags").get("models", [])
        if not isinstance(tags, list) or any(not isinstance(m, dict) for m in tags):
            raise RetrievalDependencyError("embedding model identity response malformed")
        matches = [m for m in tags if m.get("name") == model or m.get("model") == model]
        if len(matches) != 1:
            raise RetrievalDependencyError("embedding model identity unavailable")
        return matches[0].get("digest")

    def embed(self, text):
        data = self.client._request(
            "POST", "/api/embeddings", {"model": self.model, "prompt": text}
        )
        vector = data.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise RetrievalDependencyError("Ollama embedding response missing non-empty embedding")
        if any(type(x) not in (int, float) for x in vector):
            raise RetrievalDependencyError("embedding vector is not numeric")
        values = [float(x) for x in vector]
        if self._dimensions is not None and len(values) != self._dimensions:
            raise RetrievalDependencyError("Ollama embedding dimension changed")
        self._dimensions = len(values)
        return values
