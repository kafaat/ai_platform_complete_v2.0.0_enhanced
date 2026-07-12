"""Cluster-safe idempotency claim for raster indicator batch jobs.

The claim key is deterministic for the immutable inputs that define a batch.
Redis ``SET NX`` is used when available; memory fallback is honest and is only
replica-local.  The stored value is the canonical job id returned to duplicate
callers so concurrent workers converge on one job instead of recomputing.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from typing import Any

CLAIM_PREFIX = "sahool:raster:indicator-batch:"
CLAIM_TTL_SECONDS = int(os.getenv("RASTER_BATCH_CLAIM_TTL_SECONDS", "86400"))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def geometry_hash(geometry: dict | None, geometry_revision: int | None) -> str:
    payload = {"geometry": geometry or None, "geometry_revision": geometry_revision}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def batch_claim_key(req: Any) -> str:
    indicators = sorted(
        {
            str(getattr(i, "value", i)).strip().lower()
            for i in req.indicators
            if str(getattr(i, "value", i)).strip()
        }
    )
    bands = (
        req.bands.model_dump(mode="json") if hasattr(req.bands, "model_dump") else dict(req.bands)
    )
    payload = {
        "tenant_id": str(req.tenant_id),
        "field_id": str(req.field_id or ""),
        "scene_id": str(req.scene_id or ""),
        "capture_datetime": str(req.capture_datetime or ""),
        "raster_url": str(req.raster_url or ""),
        "source_format": str(getattr(req.source_format, "value", req.source_format)),
        "indicators": indicators,
        "bands": bands,
        "geometry_hash": geometry_hash(req.clip_polygon_geojson, req.geometry_revision),
        "apply_cloud_mask": bool(req.apply_cloud_mask),
        "raw_qa_required": bool(req.raw_qa_required),
        "min_raw_quality_score": float(req.min_raw_quality_score),
    }
    return "rib_" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ClaimResult:
    acquired: bool
    job_id: str
    backend: str


class BatchClaimStore:
    def __init__(self, redis_url: str | None = None):
        self._mem: dict[str, str] = {}
        self._lock = threading.Lock()
        self._redis = None
        if redis_url:
            try:
                import redis

                client = redis.Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
                client.ping()
                self._redis = client
            except Exception:
                self._redis = None

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def claim(self, key: str, job_id: str) -> ClaimResult:
        redis_key = CLAIM_PREFIX + key
        if self._redis is not None:
            acquired = bool(self._redis.set(redis_key, job_id, nx=True, ex=CLAIM_TTL_SECONDS))
            if acquired:
                return ClaimResult(True, job_id, "redis")
            existing = self._redis.get(redis_key)
            return ClaimResult(False, str(existing or job_id), "redis")
        with self._lock:
            existing = self._mem.get(key)
            if existing is not None:
                return ClaimResult(False, existing, "memory")
            self._mem[key] = job_id
            return ClaimResult(True, job_id, "memory")

    def release(self, key: str, job_id: str) -> bool:
        redis_key = CLAIM_PREFIX + key
        if self._redis is not None:
            # Compare-and-delete so one worker cannot release another worker's claim.
            script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
            return bool(self._redis.eval(script, 1, redis_key, job_id))
        with self._lock:
            if self._mem.get(key) != job_id:
                return False
            self._mem.pop(key, None)
            return True

    def clear(self) -> None:
        with self._lock:
            self._mem.clear()


BATCH_CLAIMS = BatchClaimStore(os.getenv("REDIS_URL"))
