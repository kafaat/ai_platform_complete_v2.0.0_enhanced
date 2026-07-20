"""Generic blob object-store (MinIO/S3) for service attachments — bytes in, key out.

Distinct from ``services/raster-service/object_store.py`` which is COG-specific
(uploads a *local file path*, GDAL env, ``upload_cog``). Season logbooks are raw
*bytes* received over HTTP, so this helper offers ``upload_bytes`` / ``object_exists``
(HEAD) / ``presigned_get_url`` — the three operations SEASON-RECORD-ENTRY-01 §4-③
needs (service-mediated upload, accept-time existence proof, short-lived read).

Fail-closed & honest about mode (reuses raster's ``S3_*`` MinIO config — no new infra):

- **S3/MinIO configured** (``S3_BUCKET`` set; ``S3_ENDPOINT`` defaults to in-cluster
  MinIO): boto3 is required; a real upload/head/presign failure raises — never a
  silent success.
- **Not configured** (dev — empty ``S3_BUCKET``): falls back to a **marked** local
  directory (``LOGBOOK_LOCAL_DIR``). The stored ref is ``file://…`` and existence is a
  real ``os.path.exists`` — so the accept-time "object must exist" proof still holds in
  dev. If S3 is configured but boto3 is missing, that raises (never a silent fallback).

The *decision* logic (mode selection, local path derivation, dev presign shape) is
importable without boto3 so it can be unit-tested; the boto3 calls are lazily
imported inside the S3 branch only.

**blob_store vs object_store (module boundary — read before adding a third caller):**
``blob_store`` is the ONE general object-storage path for the platform henceforth —
raw bytes, any service, ``upload_bytes``/``object_exists``/``presigned_get_url``.
``object_store`` (raster-service) is the raster/COG *specialisation* only (local-file
COG upload, GDAL env). New general storage goes through ``blob_store``; do not grow a
third helper. Both read the SAME shared ``S3_*`` MinIO config (the established
platform convention — decision-service/raster/others already use it), so there is no
per-slice env and no cross-service key smuggling: it is one shared store, by design.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("shared.storage.blob_store")

# ── configuration (env) — the SHARED platform MinIO convention (no new vars) ─────
# S3_BUCKET is the enable switch (empty ⇒ dev file:// fallback). S3_ENDPOINT carries a
# non-empty in-cluster default. S3_USE_SSL controls the scheme explicitly (never a silent
# http:// guess — condition ②). Keys are the shared platform creds (condition ③ reversed:
# S3_* is the platform-wide convention, not raster's private keys).
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "")
S3_USE_SSL = os.getenv("S3_USE_SSL", "false")
# Explicit degradation gate (mirrors object_store): when S3 is configured but a real
# upload can't happen (missing keys / put failure), fail-closed by default; only degrade
# to file:// with a HIGH warning when S3_ALLOW_FILE_FALLBACK=1 (dev). Never a silent drop.
S3_ALLOW_FILE_FALLBACK = os.getenv("S3_ALLOW_FILE_FALLBACK", "false")
# Dev fallback directory (marked file:// refs). Never used when S3 is enabled.
LOCAL_DIR = os.getenv("LOGBOOK_LOCAL_DIR", "/tmp/sahool-logbooks")

# Hosts treated as in-cluster/local (http acceptable). Anything else + http ⇒ high warn.
_INTERNAL_HOST_MARKERS = ("sahool-minio", "minio", "localhost", "127.0.0.1", "::1")


class BlobStoreError(RuntimeError):
    """Raised on a real (non-dev-fallback) object-store failure — never swallowed."""


def _use_ssl() -> bool:
    return str(S3_USE_SSL).strip().lower() in ("1", "true", "yes", "on")


def _allow_file_fallback() -> bool:
    return str(S3_ALLOW_FILE_FALLBACK).strip().lower() in ("1", "true", "yes", "on")


def s3_enabled() -> bool:
    """True iff S3 is configured (bucket is the switch; endpoint must accompany it).

    Empty ``S3_BUCKET`` -> dev file:// fallback (same contract as raster
    ``object_store.enabled()``). This does NOT conflate empty (dev) with broken:
    a bucket set WITHOUT an endpoint is a misconfiguration surfaced by
    :func:`_require_reachable_config`, not a silent fallback (condition ①).
    """
    return bool(S3_BUCKET.strip()) and bool(S3_ENDPOINT.strip())


def _require_reachable_config() -> None:
    """Condition ①: BUCKET set but ENDPOINT empty is *broken*, not dev — fail-closed.

    Empty bucket is the legitimate dev state (handled by :func:`s3_enabled` -> file://);
    a set bucket with no endpoint would silently drop to file:// and think itself
    production. That mismatch is rejected loudly instead.
    """
    if S3_BUCKET.strip() and not S3_ENDPOINT.strip():
        raise BlobStoreError(
            "S3_BUCKET is set but S3_ENDPOINT is empty — misconfigured object store "
            "(set S3_ENDPOINT, or clear S3_BUCKET for dev file:// storage)"
        )


def _endpoint_url() -> str:
    """Full URL with an EXPLICIT scheme from S3_USE_SSL (never a silent http guess)."""
    ep = S3_ENDPOINT.strip()
    host = ep
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
            break
    host = host.rstrip("/")
    scheme = "https" if _use_ssl() else "http"
    # Condition ②: external host over plaintext http ⇒ attachments/creds travel exposed.
    external = not any(m in host for m in _INTERNAL_HOST_MARKERS)
    if scheme == "http" and external:
        logger.warning(
            "blob_store: S3_ENDPOINT '%s' is an EXTERNAL host over plaintext http — "
            "logbook bytes and credentials travel unencrypted; set S3_USE_SSL=true",
            host,
        )
    return f"{scheme}://{host}"


def _local_path_for(key: str) -> str:
    """Dev on-disk path for an object key (under LOCAL_DIR, key nesting preserved)."""
    return os.path.join(LOCAL_DIR, key)


def _s3_client():
    # Config validation first (independent of boto3): a mis-provisioned store must not
    # pretend to work — missing creds fail-closed regardless of whether boto3 is present.
    access_key = os.getenv("S3_ACCESS_KEY")
    secret_key = os.getenv("S3_SECRET_KEY")
    if not access_key or not secret_key:
        raise BlobStoreError(
            "S3_BUCKET/S3_ENDPOINT are configured but S3_ACCESS_KEY/S3_SECRET_KEY are missing"
        )
    try:
        import boto3  # lazy — only the S3 branch needs it
    except ImportError as exc:  # boto3 must be present when S3 is configured
        raise BlobStoreError("S3 configured but boto3 is not installed") from exc
    return boto3.client(
        "s3",
        endpoint_url=_endpoint_url(),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def upload_bytes(key: str, data: bytes, content_type: str) -> str:
    """Store ``data`` under ``key``; return the internal ref (``s3://…`` or ``file://…``).

    The ref is what goes into ``logbook_image_ref`` — never handed to a client.
    """
    _require_reachable_config()  # ①: bucket-without-endpoint is broken, not dev
    if s3_enabled():
        try:
            client = _s3_client()  # raises on missing keys (fail-closed)
            client.put_object(Bucket=S3_BUCKET, Key=key, Body=data, ContentType=content_type)
        except BlobStoreError:
            raise
        except Exception as exc:  # noqa: BLE001 — real S3 error
            if not _allow_file_fallback():
                raise BlobStoreError(
                    f"S3 put_object failed for s3://{S3_BUCKET}/{key}: {exc}"
                ) from exc
            logger.warning(
                "blob_store: S3 upload failed for s3://%s/%s — S3_ALLOW_FILE_FALLBACK ⇒ file:// "
                "(dev degradation, NOT servable): %s",
                S3_BUCKET,
                key,
                exc,
            )
        else:
            return f"s3://{S3_BUCKET}/{key}"
    # dev fallback — marked local file (or gated degradation above)
    path = _local_path_for(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return f"file://{path}"


def object_exists(ref: str) -> bool:
    """HEAD the object behind an internal ref. Used at accept-time (§ closing proof).

    A ``logbook_image_ref`` that points at nothing (dead ref) -> accept rejected
    ``logbook_missing``. Fail-closed: any S3 error other than a clean 404 is treated
    as "cannot prove it exists" -> False, so acceptance never proceeds on doubt.
    """
    if not ref:
        return False
    if ref.startswith("file://"):
        # ②: a file:// ref in an S3-configured (production) deployment is a dev remnant or
        # forgery — the container FS is ephemeral and the file may live in another container.
        # os.path.exists would be a phantom proof, so reject it; accept sees logbook_missing.
        if s3_enabled():
            return False
        return os.path.exists(ref[len("file://") :])
    if ref.startswith("s3://"):
        if not s3_enabled():
            return False  # an s3:// ref with S3 now disabled cannot be proven -> reject
        bucket, _, obj_key = ref[len("s3://") :].partition("/")
        client = _s3_client()
        try:
            client.head_object(Bucket=bucket, Key=obj_key)
            return True
        except Exception:  # noqa: BLE001 — 404 or any error -> cannot prove existence
            return False
    return False


def presigned_get_url(ref: str, ttl_s: int) -> str:
    """Short-lived read URL for an internal ref (never expose the raw key/ref).

    In S3 mode returns a presigned GET (expires in ``ttl_s``). In dev (file://) there
    is no signing origin, so returns the ``file://`` ref itself, marked — callers/tests
    must treat a ``file://`` result as dev-only, not a shareable URL.

    ①: the ≤300s contract TTL is enforced *inside* this function (deep defence) so the
    unit guard stays honest even if a future caller passes 3600 — cheaper than chasing
    every call site.
    """
    if ttl_s <= 0 or ttl_s > 300:
        raise BlobStoreError(f"presign TTL out of contract: {ttl_s}s (max 300s)")
    if ref.startswith("s3://"):
        if not s3_enabled():
            raise BlobStoreError("cannot presign an s3:// ref while S3 is disabled")
        bucket, _, obj_key = ref[len("s3://") :].partition("/")
        client = _s3_client()
        try:
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": obj_key},
                ExpiresIn=int(ttl_s),
            )
        except Exception as exc:  # noqa: BLE001
            raise BlobStoreError(f"presign failed for {ref}: {exc}") from exc
    if ref.startswith("file://"):
        return ref  # dev-only; not a network-shareable URL
    raise BlobStoreError(f"unsupported logbook ref scheme: {ref!r}")
