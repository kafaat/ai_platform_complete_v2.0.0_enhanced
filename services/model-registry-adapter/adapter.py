"""WX-12 registry adapter.

Consumes authoritative activation/rollback commands from decision-service and performs a
compare-and-swap against a configured registry HTTP API. Production is fail-closed: only the
certified HTTP backend is accepted when SAHOOL_ENV=production (no local/offline substitute).
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

TRUTHY = {"1", "true", "yes", "on"}


class RegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegistryState:
    alias: str
    artifact_uri: str
    artifact_digest: str
    version: str | None = None


class HttpRegistry:
    def __init__(self) -> None:
        self.base = os.getenv("MODEL_REGISTRY_URL", "").rstrip("/")
        self.token = os.getenv("MODEL_REGISTRY_TOKEN", "")
        if not self.base:
            raise RegistryError("MODEL_REGISTRY_URL is required")
        if os.getenv("SAHOOL_ENV", "").lower() == "production" and not self.token:
            raise RegistryError("MODEL_REGISTRY_TOKEN is required in production")

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = (
            None
            if body is None
            else json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        )
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(
                req, timeout=float(os.getenv("MODEL_REGISTRY_TIMEOUT_SECONDS", "10"))
            ) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            raise RegistryError(
                f"registry http {e.code}: {e.read().decode(errors='replace')[:500]}"
            ) from e

    def get(self, model_id: str, environment: str, alias: str) -> RegistryState:
        obj = self._request("GET", f"/v1/models/{model_id}/aliases/{environment}/{alias}")
        return RegistryState(alias, obj["artifact_uri"], obj["artifact_digest"], obj.get("version"))

    def compare_and_swap(
        self,
        *,
        model_id: str,
        environment: str,
        alias: str,
        expected_digest: str,
        artifact_uri: str,
        artifact_digest: str,
    ) -> RegistryState:
        obj = self._request(
            "POST",
            f"/v1/models/{model_id}/aliases/{environment}/{alias}:cas",
            {
                "expected_artifact_digest": expected_digest,
                "artifact_uri": artifact_uri,
                "artifact_digest": artifact_digest,
            },
        )
        state = RegistryState(
            alias, obj["artifact_uri"], obj["artifact_digest"], obj.get("version")
        )
        if state.artifact_digest != artifact_digest:
            raise RegistryError("registry returned a digest different from requested artifact")
        return state


def token_hash(token: str) -> str:
    if len(token) < 24:
        raise RegistryError("delivery token must contain at least 24 characters")
    return hashlib.sha256(token.encode()).hexdigest()


def validate_runtime() -> None:
    backend = os.getenv("MODEL_REGISTRY_BACKEND", "http")
    if backend != "http":
        raise RegistryError("only MODEL_REGISTRY_BACKEND=http is certified")
    if (
        os.getenv("SAHOOL_ENV", "").lower() == "production"
        and os.getenv("MODEL_REGISTRY_DRY_RUN", "true").lower() in TRUTHY
    ):
        raise RegistryError("MODEL_REGISTRY_DRY_RUN must be false in production")
    HttpRegistry()
