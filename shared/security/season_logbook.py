"""SEASON-RECORD-ENTRY-01 §4-③ — logbook attachment content-safety helpers (pure).

The logbook attachment is the single human "signature" that gates season
acceptance (§3), so its handling must not trust the client. Two rules the owner
made binding:

- **Content, not extension** — the accepted type is decided from the file's
  *magic bytes* (JPEG ``FF D8 FF`` / PNG ``89 50 4E 47`` / PDF ``25 50 44 46``),
  never the client-supplied ``Content-Type`` or the ``.jpg`` in the filename. A
  ``.jpg`` whose bytes are not JPEG is rejected.
- **Size measured after receipt** — the ``Content-Length`` header is a claim; the
  gate is the number of bytes actually streamed. ``MAX_LOGBOOK_BYTES`` caps it.

The object key is **server-derived** (tenant + season_id + content sha) so the
client can neither pick the storage path nor smuggle one season's attachment
under another season's id. ``logbook_image_ref`` stores this internal key and is
never handed to the client; access is via short-lived presigned URLs
(``PRESIGN_TTL_S``).

Stdlib-only (no FastAPI / no boto3) so the decision logic is unit-testable in the
no-fastapi CI tier; the service wires it to the real upload/object-store in the
endpoint layer (slice 2b).
"""

from __future__ import annotations

import hashlib

# Size gate — measured on the bytes actually received, never Content-Length.
MAX_LOGBOOK_BYTES = 10 * 1024 * 1024  # 10 MiB

# Presigned-URL lifetime ceiling (§4-③: access via short-lived URLs, key never leaked).
PRESIGN_TTL_S = 300  # 5 minutes

# Stable rejection codes surfaced by the endpoint layer.
ERROR_LOGBOOK_UNSUPPORTED_TYPE = "logbook_unsupported_type"  # magic bytes not JPEG/PNG/PDF -> 415
ERROR_LOGBOOK_TOO_LARGE = "logbook_too_large"  # bytes received exceed MAX_LOGBOOK_BYTES -> 413
ERROR_LOGBOOK_MISSING = "logbook_missing"  # accept-time: object key has no backing object -> reject

# Magic-byte signature -> canonical (content_type, extension). Order matters only
# for readability; each prefix is unambiguous.
_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"%PDF-", "application/pdf", "pdf"),
)

# Longest signature we must see to classify — the endpoint only needs to sniff
# this many leading bytes (cheap, before streaming the whole body).
MAGIC_SNIFF_BYTES = max(len(sig) for sig, _, _ in _MAGIC)


def detect_content_type(head: bytes | None) -> tuple[str, str] | None:
    """Classify by magic bytes. Returns ``(content_type, ext)`` or ``None``.

    ``None`` means the leading bytes match no allowed signature -> the endpoint
    rejects with ``logbook_unsupported_type`` (415). A client-supplied MIME type
    or filename extension is deliberately NOT consulted.
    """
    if not head:
        return None
    for sig, content_type, ext in _MAGIC:
        if head.startswith(sig):
            return content_type, ext
    return None


def logbook_size_ok(num_bytes: int) -> bool:
    """True iff the count of bytes actually received is within the cap (fail-closed)."""
    return 0 < num_bytes <= MAX_LOGBOOK_BYTES


def derive_logbook_key(tenant_id: str, season_id: str, content_sha256: str, ext: str) -> str:
    """Server-derived object key: ``season-logbooks/<tenant>/<season_id>/<sha>.<ext>``.

    Every component is server-controlled: ``tenant_id`` from the gateway-trusted
    header, ``season_id`` from the pinned path/row (not the client body), the sha
    from the received bytes, and ``ext`` from :func:`detect_content_type` (magic
    bytes) — never the client filename. Embedding ``season_id`` means an object
    can never be addressed under a different season than the one it was uploaded
    for.
    """
    t = (tenant_id or "").strip()
    s = (season_id or "").strip()
    sha = (content_sha256 or "").strip()
    if not t or not s or not sha or not ext:
        raise ValueError("derive_logbook_key requires tenant_id, season_id, sha, ext")
    return f"season-logbooks/{t}/{s}/{sha}.{ext}"


def content_sha256(data: bytes) -> str:
    """Hex sha-256 of the received bytes (used both as key component and dedup)."""
    return hashlib.sha256(data).hexdigest()


def key_belongs_to(key: str, tenant_id: str, season_id: str) -> bool:
    """Ownership check for presigned-GET: the key must sit under this tenant+season.

    Defence in depth behind RLS — a presigned GET request is only issued for a
    ``logbook_image_ref`` whose derived prefix matches the caller's trusted tenant
    and the pinned season, so a cross-tenant/cross-season ref cannot be signed.
    """
    t = (tenant_id or "").strip()
    s = (season_id or "").strip()
    if not key or not t or not s:
        return False
    return key.startswith(f"season-logbooks/{t}/{s}/")
