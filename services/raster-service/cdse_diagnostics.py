"""Bounded, restart-persistent CDSE failure receipts on the raster volume.

Only allowlisted observations and hashes are retained, never provider bodies,
headers, exception text, credentials or raster bytes. This is a rolling window
of 256 distinct/recent failures after successful rotation (at most one extra
after interruption). Exact repeated observations reuse a receipt for 60 seconds
without refreshing its timestamp or counting repetitions. This is not an archive
or proof of a durable production mount.
The historical empty-scene incident cannot be reconstructed by this recorder.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import raster_settings

MAX_RECEIPTS = 256
MAX_RECEIPT_BYTES = 8192
DUPLICATE_WINDOW_SECONDS = 60
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
_SEMANTIC_FIELDS = (
    "schema",
    "provider",
    "outcome",
    "stage",
    "attribution",
    "historical_cause",
    "request",
    "response",
)
_REQUEST_FIELDS = {
    "tenant_sha256",
    "field_sha256",
    "index_sha256",
    "date_from",
    "date_to",
    "bbox",
    "geometry_sha256",
    "max_cloud_pct",
}
# What the catalogue said about the request window when it was asked without the
# tile-level cloud filter. ``not_available`` means it was not asked.
_CATALOGUE_EVIDENCE = {
    "not_available",
    "catalogue_unavailable",
    "no_acquisition",
    "acquisitions_above_cloud_limit",
    "acquisitions_within_cloud_limit",
    "acquisitions_cloud_cover_unknown",
}
# Outcomes where "was there anything to observe?" is the open question.
CATALOGUE_PROBE_OUTCOMES = frozenset({"empty_raster", "no_selected_scene"})
CATALOGUE_PROBE_TTL_SECONDS = 300
CATALOGUE_PROBE_MAX_ENTRIES = 256
_probe_cache: dict[str, tuple[float, str]] = {}
_RESPONSE_FIELDS = {
    "http_status",
    "bytes",
    "sha256",
    "scene_id_sha256",
    "catalogue_evidence",
    "before_mask",
    "after_mask",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


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


def catalogue_evidence(scenes, max_cloud_pct) -> str:
    """Classify a catalogue answer fetched **without** the cloud filter.

    Only a successful search reaches here; an outage is ``catalogue_unavailable``
    and is never read as "no acquisition".
    """
    if not isinstance(scenes, list):
        return "catalogue_unavailable"
    if not scenes:
        return "no_acquisition"
    within = unknown = 0
    for scene in scenes:
        props = scene.get("properties") if isinstance(scene, dict) else None
        raw = props.get("eo:cloud_cover") if isinstance(props, dict) else None
        if type(raw) in (int, float) and math.isfinite(raw) and 0 <= raw <= 100:
            within += raw <= max_cloud_pct
        else:
            unknown += 1
    if within:
        return "acquisitions_within_cloud_limit"
    if unknown:
        return "acquisitions_cloud_cover_unknown"
    return "acquisitions_above_cloud_limit"


def catalogue_probe_enabled() -> bool:
    """Off unless ``CDSE_DIAGNOSTIC_CATALOGUE_PROBE=1``: it adds a provider call."""
    return os.getenv("CDSE_DIAGNOSTIC_CATALOGUE_PROBE", "0").strip() == "1"


def probe_key(bbox, geometry, date_from, date_to, max_cloud_pct) -> str:
    return _digest([list(bbox), geometry, str(date_from), str(date_to), max_cloud_pct])


def cached_probe(key: str, now: float | None = None) -> str | None:
    """A recent answer for the same window, so a field whose tiles keep failing
    does not turn every map tile into a catalogue request."""
    clock = _utc_now().timestamp() if now is None else now
    cached = _probe_cache.get(key)
    return cached[1] if cached and cached[0] > clock else None


def remember_probe(key: str, evidence: str, now: float | None = None) -> str:
    clock = _utc_now().timestamp() if now is None else now
    if evidence not in _CATALOGUE_EVIDENCE:
        evidence = "not_available"
    if key not in _probe_cache and len(_probe_cache) >= CATALOGUE_PROBE_MAX_ENTRIES:
        _probe_cache.pop(min(_probe_cache, key=lambda k: _probe_cache[k][0]))
    _probe_cache[key] = (clock + CATALOGUE_PROBE_TTL_SECONDS, evidence)
    return evidence


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
    catalogue="not_available",
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
    catalogue = catalogue if catalogue in _CATALOGUE_EVIDENCE else "not_available"
    if attribution == "unknown" and outcome in CATALOGUE_PROBE_OUTCOMES:
        # Only a catalogue answer can say there was nothing to observe. Zero
        # observable pixels alone never decide between absence, cloud and mask.
        if catalogue == "no_acquisition":
            attribution = "no_acquisition_in_window"
        elif catalogue == "acquisitions_above_cloud_limit":
            attribution = "filtered_by_tile_cloud_cover"
    raw = payload if isinstance(payload, bytes) else None
    return {
        "schema": "sahool.cdse-failure-receipt.v1",
        "receipt_id": uuid4().hex,
        "observed_at": _utc_now().isoformat(),
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
            "catalogue_evidence": catalogue,
            "before_mask": before,
            "after_mask": after,
        },
        "retention": {
            "kind": "rolling_failure_window",
            "max_receipts": MAX_RECEIPTS,
            "max_unrotated_receipts": MAX_RECEIPTS + 1,
            "max_receipt_bytes": MAX_RECEIPT_BYTES,
            "duplicate_window_seconds": DUPLICATE_WINDOW_SECONDS,
        },
    }


def _sync_directory(root: Path) -> None:
    dir_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _semantic_key(receipt) -> str | None:
    """Compare only the supported allowlisted schema, never arbitrary disk data."""
    if not isinstance(receipt, dict) or set(receipt) != set(_SEMANTIC_FIELDS) | {
        "receipt_id",
        "observed_at",
        "retention",
    }:
        return None
    if (
        receipt["schema"] != "sahool.cdse-failure-receipt.v1"
        or receipt["provider"] != "cdse"
        or receipt["historical_cause"] != "not_reconstructed"
        or not isinstance(receipt["outcome"], str)
        or receipt["outcome"] not in _OUTCOMES | {"unknown"}
        or not isinstance(receipt["request"], dict)
        or set(receipt["request"]) != _REQUEST_FIELDS
        or not isinstance(receipt["response"], dict)
        or set(receipt["response"]) != _RESPONSE_FIELDS
        or not isinstance(receipt["retention"], dict)
    ):
        return None
    retention = receipt["retention"]
    limits = {"max_receipts", "max_unrotated_receipts", "max_receipt_bytes"}
    required = limits | {"kind"}
    if (
        set(retention) not in (required, required | {"duplicate_window_seconds"})
        or retention["kind"] != "rolling_failure_window"
        or any(type(retention[k]) is not int or retention[k] < 1 for k in limits)
        or retention["max_unrotated_receipts"] != retention["max_receipts"] + 1
        or retention.get("duplicate_window_seconds", DUPLICATE_WINDOW_SECONDS)
        != DUPLICATE_WINDOW_SECONDS
    ):
        return None
    return json.dumps({k: receipt[k] for k in _SEMANTIC_FIELDS}, sort_keys=True, allow_nan=False)


def _unique_keys(pairs) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("diagnostic_duplicate_json_key")
        result[key] = value
    return result


def _recent_duplicate(files: list[tuple[int, Path]], receipt: dict) -> str | None:
    expected = _semantic_key(receipt)
    if expected is None:
        return None
    now = _utc_now()
    # Disk reads and parsing are bounded, and special files/symlinks are never
    # followed. No receipt contents or parse errors are copied into logs.
    for _, path in reversed(files[-MAX_RECEIPTS:]):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    continue
                data = stream.read(MAX_RECEIPT_BYTES + 1)
            if len(data) > MAX_RECEIPT_BYTES:
                continue
            previous = json.loads(data, object_pairs_hook=_unique_keys)
            if _semantic_key(previous) != expected or previous["receipt_id"] != path.stem:
                continue
            observed = datetime.fromisoformat(previous["observed_at"])
            if observed.tzinfo is None:
                continue
            age = (now - observed).total_seconds()
            if 0 <= age < DUPLICATE_WINDOW_SECONDS:
                return path.stem
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
            # Damaged or unsupported historical data cannot suppress evidence.
            continue
    return None


def persist(receipt: dict) -> str:
    """Atomically retain a bounded receipt; raise if durability cannot be established.

    The caller reports failure without retaining raw provider bytes as a fallback.
    File and directory fsync cover local restart durability; mount/backup/retention
    verification on a deployment is still required. All processes sharing this
    POSIX volume serialize retention and writes with the same advisory lock.
    Commit the replacement before rotation: an interrupted rotation may retain
    one extra record, reconciled before another append. Never discard old
    evidence to make room for a write whose durability is not established.
    An exact semantic duplicate within a fixed 60-second window returns the
    earlier receipt ID. Its original observation time is not refreshed; no new
    observation or repetition count is claimed. Directory fsync still confirms
    durability even if the preceding writer failed after its atomic rename.
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
            ((p.lstat().st_mtime_ns, p) for p in root.iterdir() if _RECEIPT_NAME.fullmatch(p.name)),
            key=lambda item: item[0],
        )
        # Reconcile a previously committed write interrupted during rotation.
        # Sync first: a previous caller may have failed at directory fsync.
        _sync_directory(root)
        recovered_rotation = len(files) > MAX_RECEIPTS
        while len(files) > MAX_RECEIPTS:
            _, oldest = files.pop(0)
            oldest.unlink()
        duplicate = _recent_duplicate(files, receipt)
        if duplicate is not None:
            if recovered_rotation:
                _sync_directory(root)
            return duplicate
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
