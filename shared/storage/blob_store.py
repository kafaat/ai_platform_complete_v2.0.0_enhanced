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

import importlib.util
import ipaddress
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit


def _load_endpoint_policy():
    """Load the sibling ``s3_endpoint_security.py`` by absolute path, never as ``shared.*``.

    ``shared`` collides with ``services/mcp_servers/shared`` (no ``storage``), so this
    module stays importable by path regardless of which ``shared`` is bound
    (``test_blob_store_immune_to_shared_package_shadow``).
    """
    path = Path(__file__).with_name("s3_endpoint_security.py")
    # Reuse the package import when it is this same file, so one EndpointPolicyError
    # class exists per process.
    canonical = sys.modules.get("shared.storage.s3_endpoint_security")
    if canonical is not None and Path(getattr(canonical, "__file__", "")) == path:
        return canonical
    name = "_sahool_storage_s3_endpoint_security"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


_endpoint_policy = _load_endpoint_policy()
EndpointPolicyError = _endpoint_policy.EndpointPolicyError
resolve_configured_s3_endpoint = _endpoint_policy.resolve_configured_s3_endpoint
require_path_style_service_root = _endpoint_policy.require_path_style_service_root

logger = logging.getLogger("shared.storage.blob_store")

# ── configuration (env) — the SHARED platform MinIO convention (no new vars) ─────
# S3_BUCKET is the enable switch (empty ⇒ dev file:// fallback). S3_ENDPOINT carries a
# non-empty in-cluster default. S3_USE_SSL controls the scheme explicitly (never a silent
# http:// guess — condition ②). Keys are the shared platform creds (condition ③ reversed:
# S3_* is the platform-wide convention, not raster's private keys).
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "")
S3_USE_SSL = os.getenv("S3_USE_SSL")
S3_ALLOW_PLAINTEXT_INTERNAL = os.getenv("S3_ALLOW_PLAINTEXT_INTERNAL", "false")
S3_ALLOW_PLAINTEXT_LOOPBACK = os.getenv("S3_ALLOW_PLAINTEXT_LOOPBACK", "false")
# SEASON-LOGBOOK-PRESIGNED-URL-SIGNED-FOR-INTERNAL-MINIO-HOST-01: the host a *client* (a
# browser) uses to reach the store. SigV4 presigned URLs sign the Host header
# (X-Amz-SignedHeaders=host), so the URL must be signed for this host from the start —
# rewriting the host of a URL signed for S3_ENDPOINT invalidates its signature. Optional;
# when empty, presign signs for S3_ENDPOINT and refuses if that host is internal-only.
S3_PUBLIC_ENDPOINT = os.getenv("S3_PUBLIC_ENDPOINT", "")
# Explicit degradation gate (mirrors object_store): when S3 is configured but a real
# upload can't happen (missing keys / put failure), fail-closed by default; only degrade
# to file:// with a HIGH warning when S3_ALLOW_FILE_FALLBACK=1 (dev). Never a silent drop.
S3_ALLOW_FILE_FALLBACK = os.getenv("S3_ALLOW_FILE_FALLBACK", "false")
# Dev fallback directory (marked file:// refs). Never used when S3 is enabled.
LOCAL_DIR = os.getenv("LOGBOOK_LOCAL_DIR", "/tmp/sahool-logbooks")


class BlobStoreError(RuntimeError):
    """Raised on a real (non-dev-fallback) object-store failure — never swallowed."""


def _s3_endpoint_decision():
    # Fail before creating a boto3 client, including when file fallback is
    # explicitly enabled. A malformed endpoint must not silently degrade.
    try:
        decision = resolve_configured_s3_endpoint(
            S3_ENDPOINT,
            S3_USE_SSL,
            S3_ALLOW_PLAINTEXT_INTERNAL,
            S3_ALLOW_PLAINTEXT_LOOPBACK,
        )
        require_path_style_service_root(decision, S3_BUCKET)
        return decision
    except EndpointPolicyError as exc:
        raise BlobStoreError(f"unsafe S3 endpoint configuration: {exc}") from exc


# Suffixes that only resolve inside a private network (Railway private networking,
# Kubernetes service DNS). Exact suffix matches, never substrings such as "minio".
_INTERNAL_ONLY_SUFFIXES = (".internal", ".svc", ".cluster.local")


def _browser_unreachable_host(host: str) -> bool:
    """True when ``host`` is a name only a private network resolves (no client can use it).

    - a single-label name (``sahool-minio``: a Compose/Docker service name) — except the
      literal ``localhost``;
    - an explicitly trusted in-cluster service identity (``TRUSTED_S3_SERVICE_HOSTS``);
    - a private-network suffix (``*.railway.internal``, ``*.svc``, ``*.cluster.local``).

    Loopback (``localhost`` / ``127.0.0.0/8`` / ``::1``) is deliberately *allowed*: the
    service can only reach a loopback store when it runs on the developer's host, which
    is the same machine as the browser, so the signed URL is usable there. Loopback HTTP
    already needs the explicit dev opt-in ``S3_ALLOW_PLAINTEXT_LOOPBACK``. IP literals are
    not classified (no RFC1918 inference, same rule as the endpoint policy).
    """
    h = host.lower().rstrip(".")
    if h == "localhost":
        return False
    try:
        ipaddress.ip_address(h)
        return False
    except ValueError:
        pass
    if h in _endpoint_policy.TRUSTED_S3_SERVICE_HOSTS:
        return True
    if "." not in h:
        return True
    return h.endswith(_INTERNAL_ONLY_SUFFIXES)


def _public_endpoint_decision():
    """Validate ``S3_PUBLIC_ENDPOINT`` with the same policy as ``S3_ENDPOINT``; None if unset.

    Same resolver (no userinfo/path/query, bare host ⇒ HTTPS, explicit scheme kept, HTTP
    only for loopback under ``S3_ALLOW_PLAINTEXT_LOOPBACK``; external HTTP forbidden) and
    the same path-style rule. ``S3_USE_SSL`` is *not* applied: it describes the internal
    hop, and an internal ``http://sahool-minio:9000`` behind a public ``https://`` origin
    is the normal shape. Plaintext-internal is never honoured here, and an internal-only
    host is rejected outright — a public endpoint nobody can resolve is a misconfiguration.
    """
    if not S3_PUBLIC_ENDPOINT.strip():
        return None
    try:
        decision = resolve_configured_s3_endpoint(
            S3_PUBLIC_ENDPOINT,
            None,
            False,
            S3_ALLOW_PLAINTEXT_LOOPBACK,
        )
        require_path_style_service_root(decision, S3_BUCKET)
    except EndpointPolicyError as exc:
        raise BlobStoreError(f"unsafe S3_PUBLIC_ENDPOINT configuration: {exc}") from exc
    if _browser_unreachable_host(decision.host):
        raise BlobStoreError(
            "S3_PUBLIC_ENDPOINT names an internal-only host; it must be a name clients resolve"
        )
    return decision


def _presign_signing_decision():
    """The endpoint a presigned URL is signed for — fail-closed when no client can use it."""
    public = _public_endpoint_decision()
    if public is not None:
        return public
    internal = _s3_endpoint_decision()
    if _browser_unreachable_host(internal.host):
        raise BlobStoreError(
            f"presign refused: S3_ENDPOINT host {internal.host!r} is internal-only and "
            "S3_PUBLIC_ENDPOINT is unset (a URL signed for it is unusable by clients)"
        )
    return internal


def _use_ssl() -> bool:
    return _s3_endpoint_decision().tls


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
    """Preserve explicit HTTPS; reject scheme/flag mismatch and unsafe HTTP."""
    return _s3_endpoint_decision().endpoint_url


def _local_path_for(key: str) -> str:
    """Dev on-disk path for an object key (under LOCAL_DIR, key nesting preserved)."""
    return os.path.join(LOCAL_DIR, key)


def _s3_client(endpoint_url: str | None = None):
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
        from botocore.client import Config
    except ImportError as exc:  # boto3 must be present when S3 is configured
        raise BlobStoreError("S3 configured but boto3 is not installed") from exc
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or _endpoint_url(),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        # Path-style, as raster's object_store: a MinIO endpoint has no per-bucket DNS.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def upload_bytes(key: str, data: bytes, content_type: str) -> str:
    """Store ``data`` under ``key``; return the internal ref (``s3://…`` or ``file://…``).

    The ref is what goes into ``logbook_image_ref`` — never handed to a client.
    """
    _require_reachable_config()  # ①: bucket-without-endpoint is broken, not dev
    if s3_enabled():
        _s3_endpoint_decision()  # config failures must not trigger dev file:// fallback
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

    SEASON-LOGBOOK-PRESIGNED-URL-SIGNED-FOR-INTERNAL-MINIO-HOST-01: the URL is signed
    for the host the client will send (``S3_PUBLIC_ENDPOINT`` when set). Without it, a
    signing host that is internal-only (``sahool-minio``) is refused with
    :class:`BlobStoreError` rather than returning a URL no client can resolve. A reverse
    proxy in front of the store must forward the public Host unchanged, or the store
    rejects the signature.
    """
    if ttl_s <= 0 or ttl_s > 300:
        raise BlobStoreError(f"presign TTL out of contract: {ttl_s}s (max 300s)")
    if ref.startswith("s3://"):
        if not s3_enabled():
            raise BlobStoreError("cannot presign an s3:// ref while S3 is disabled")
        bucket, _, obj_key = ref[len("s3://") :].partition("/")
        signing = _presign_signing_decision()  # before any client: config fails first
        client = _s3_client(signing.endpoint_url)
        try:
            url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": obj_key},
                ExpiresIn=int(ttl_s),
            )
        except Exception as exc:  # noqa: BLE001
            raise BlobStoreError(f"presign failed for {ref}: {exc}") from exc
        # The signature covers the host; a URL for any other host is unusable — refuse it.
        if (urlsplit(url).hostname or "").lower() != signing.host:
            raise BlobStoreError("presign produced a URL for a host other than the signing host")
        return url
    if ref.startswith("file://"):
        return ref  # dev-only; not a network-shareable URL
    raise BlobStoreError(f"unsupported logbook ref scheme: {ref!r}")
