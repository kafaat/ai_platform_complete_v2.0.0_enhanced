"""Bounded, restart-persistent CDSE failure receipts on the raster volume.

Only allowlisted observations and hashes are retained, never provider bodies,
headers, exception text, credentials or raster bytes. This is a rolling window
of 256 failures after successful rotation (at most one extra after interruption),
not an archive or proof of a durable production mount.
The historical empty-scene incident cannot be reconstructed by this recorder.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import raster_settings

MAX_RECEIPTS = 256
MAX_RECEIPT_BYTES = 8192
_RECEIPT_NAME = re.compile(r"^[0-9a-f]{32}\.json$")
_TEMP_NAME = re.compile(r"^[0-9a-f]{32}\.tmp$")
_OUTCOMES = {
    "empty_raster",
    "mask_failed",
    "provider_error",
    "content_check_failed",
    "content_rejected",
    "no_selected_scene",
    "client_unavailable",
    "request_invalid",
    "runtime_failure",
}


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _date(value) -> str | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat()
    except (ValueError, TypeError):
        return None


def _observation(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    count = value.get("observable_pixels")
    return {
        "readable": value.get("readable") is True,
        "observable_pixels": count if type(count) is int and count >= 0 else None,
    }


def failure_receipt(
    *,
    tenant,
    field_id,
    index,
    date_from,
    date_to,
    bbox,
    geometry,
    max_cloud_pct,
    outcome,
    payload=None,
    before_mask=None,
    after_mask=None,
    error=None,
    scene_id=None,
    quota_exhausted=False,
    stage="unknown",
) -> dict:
    """Separate a request's parameters from actually observed response evidence."""
    clean_bbox = None
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        if all(type(v) in (int, float) and math.isfinite(v) for v in bbox):
            clean_bbox = list(bbox)
    status = None
    attribution = "unknown"
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status == 401:
            attribution = "authentication_rejected"
        elif status == 403:
            # A generic 403 does not prove insufficient scope (it can be quota,
            # policy, or another rejection). Do not retain the challenge itself.
            challenge = error.response.headers.get("WWW-Authenticate", "")
            attribution = (
                "scope_rejected"
                if re.search(r'\berror\s*=\s*"insufficient_scope"', challenge, re.I)
                else "forbidden_reason_unknown"
            )
        elif status == 429:
            attribution = "rate_limited"
        elif status in {500, 502, 503, 504}:
            attribution = "provider_transient_failure"
    elif isinstance(error, httpx.TransportError):
        attribution = "transport_failure"
    if quota_exhausted:
        attribution = "processing_quota_exhausted"
    before, after = _observation(before_mask), _observation(after_mask)
    if (
        outcome == "empty_raster"
        and before
        and after
        and before["readable"]
        and after["readable"]
        and (before["observable_pixels"] or 0) > 0
        and after["observable_pixels"] == 0
    ):
        attribution = "polygon_mask_removed_observations"
    raw = payload if isinstance(payload, bytes) else None
    return {
        "schema": "sahool.cdse-failure-receipt.v1",
        "receipt_id": uuid4().hex,
        "observed_at": datetime.now(UTC).isoformat(),
        "provider": "cdse",
        "outcome": outcome if outcome in _OUTCOMES else "unknown",
        "stage": stage
        if stage
        in {"client", "catalogue", "process", "local_file", "mask", "content_check", "cache"}
        else "unknown",
        "attribution": attribution,
        "historical_cause": "not_reconstructed",
        "request": {
            "tenant_sha256": _digest(tenant),
            "field_sha256": _digest(field_id),
            "index_sha256": _digest(index),
            "date_from": _date(date_from),
            "date_to": _date(date_to),
            "bbox": clean_bbox,
            "geometry_sha256": _digest(geometry) if geometry else None,
            "max_cloud_pct": max_cloud_pct
            if type(max_cloud_pct) in (int, float) and math.isfinite(max_cloud_pct)
            else None,
        },
        "response": {
            "http_status": status,
            "bytes": len(raw) if raw is not None else None,
            "sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
            "scene_id_sha256": _digest(scene_id) if scene_id else None,
            "catalogue_evidence": "not_available",
            "before_mask": before,
            "after_mask": after,
        },
        "retention": {
            "kind": "rolling_failure_window",
            "max_receipts": MAX_RECEIPTS,
            "max_unrotated_receipts": MAX_RECEIPTS + 1,
            "max_receipt_bytes": MAX_RECEIPT_BYTES,
        },
    }


def _sync_directory(root: Path) -> None:
    dir_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def persist(receipt: dict) -> str:
    """Atomically retain a bounded receipt; raise if durability cannot be established.

    The caller reports failure without retaining raw provider bytes as a fallback.
    File and directory fsync cover local restart durability; mount/backup/retention
    verification on a deployment is still required. All processes sharing this
    POSIX volume serialize retention and writes with the same advisory lock.
    Commit the replacement before rotation: an interrupted rotation may retain
    one extra record, reconciled before another append. Never discard old
    evidence to make room for a write whose durability is not established.
    """
    data = (
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    ).encode()
    if len(data) > MAX_RECEIPT_BYTES:
        raise ValueError("diagnostic_receipt_too_large")
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not re.fullmatch(r"[0-9a-f]{32}", receipt_id):
        raise ValueError("diagnostic_receipt_id_invalid")
    root = Path(raster_settings.UPLOAD_DIR) / "cdse_diagnostics"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Lock and receipt permissions prevent serving diagnostic context to other
    # container users. No tenant-supplied string is ever used as a path segment.
    lock_fd = os.open(root / "write.lock", os.O_CREAT | os.O_RDWR, 0o600)
    temp = root / (receipt_id + ".tmp")
    final = root / (receipt_id + ".json")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        # No live writer owns a temporary receipt while this lock is held.
        # Remove only our own interrupted writes, so crash/retry cannot grow
        # abandoned .tmp files outside the receipt bound.
        for path in root.iterdir():
            if _TEMP_NAME.fullmatch(path.name):
                path.unlink()
        files = sorted(
            ((p.stat().st_mtime_ns, p) for p in root.iterdir() if _RECEIPT_NAME.fullmatch(p.name)),
            key=lambda item: item[0],
        )
        # Reconcile a previously committed write interrupted during rotation.
        # Sync first: a previous caller may have failed at directory fsync.
        _sync_directory(root)
        while len(files) > MAX_RECEIPTS:
            _, oldest = files.pop(0)
            oldest.unlink()
        _sync_directory(root)
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, final)
        _sync_directory(root)
        # The new receipt is durable before the oldest record is removed.
        while len(files) >= MAX_RECEIPTS:
            _, oldest = files.pop(0)
            oldest.unlink()
        _sync_directory(root)
        return receipt_id
    finally:
        try:
            temp.unlink(missing_ok=True)
        finally:
            os.close(lock_fd)
