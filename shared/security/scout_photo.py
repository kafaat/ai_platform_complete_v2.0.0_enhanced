"""Proof-of-bytes contract for uploaded scouting photographs (v260 ``scout_photo_evidence``).

Trust boundary: a valid image and matching SHA-256 prove the received *bytes*, not disease
identity, capture time, user provenance, or agronomic approval.

Everything here is pure (no database, no object store), so the HTTP layer in
``services/scout-ingest-service/media_api.py`` only wires these decisions to I/O.
"""

from __future__ import annotations

import hashlib
import io
import re
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from PIL import Image, UnidentifiedImageError

MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_PHOTO_PIXELS = 25_000_000
_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_PIL_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
_SHA = re.compile(r"^[0-9a-f]{64}$")
# Same alphabet and length as the phone's DeviceLocalPhotoStore.isValidPinId.
_SAFE_PIN = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")
MEDIA_PREFIX = "scouting-photos/v1"

# Codes a client can fix by sending another file (415), as opposed to a malformed request (422).
_UNSUPPORTED_CODES = frozenset(
    {"unsupported_photo_type", "photo_type_mismatch", "photo_decode_failed"}
)


class PhotoValidationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PhotoInfo:
    sha256: str
    content_type: str
    size_bytes: int
    width: int
    height: int


def media_key(tenant_id: str, pin_id: str, sha256: str) -> str:
    """Server-derived key; no caller-controlled path separators or S3 prefixes."""
    try:
        tenant = str(UUID(str(tenant_id)))
    except (TypeError, ValueError):
        raise PhotoValidationError("invalid_media_key") from None
    if not isinstance(pin_id, str) or not _SAFE_PIN.fullmatch(pin_id):
        raise PhotoValidationError("invalid_media_key")
    if not isinstance(sha256, str) or not _SHA.fullmatch(sha256):
        raise PhotoValidationError("invalid_media_key")
    return f"{MEDIA_PREFIX}/{tenant}/{pin_id}/{sha256}"


def valid_pin_id(pin_id: str) -> bool:
    return isinstance(pin_id, str) and bool(_SAFE_PIN.fullmatch(pin_id))


def http_status_for(code: str) -> int:
    """HTTP status for a :class:`PhotoValidationError` code (an oversized body is 413 earlier)."""
    return 415 if code in _UNSUPPORTED_CODES else 422


def inspect_photo(data: bytes, claimed_type: str, claimed_sha256: str) -> PhotoInfo:
    """Bounded, fully decoded JPEG/PNG/WebP with a mandatory matching upload hash."""
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise PhotoValidationError("photo_size_invalid")
    if claimed_type not in _IMAGE_TYPES:
        raise PhotoValidationError("unsupported_photo_type")
    if not _SHA.fullmatch(claimed_sha256 or ""):
        raise PhotoValidationError("photo_sha256_required")
    digest = hashlib.sha256(data).hexdigest()
    if digest != claimed_sha256:
        raise PhotoValidationError("photo_sha256_mismatch")
    # Pillow decodes the image, not merely extension/magic. Reject bombs and malformed
    # streams (including short, forged JPEG headers). No transcoding/EXIF mutation.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as im:
                width, height = im.size
                if width < 1 or height < 1 or width * height > MAX_PHOTO_PIXELS:
                    raise PhotoValidationError("photo_pixel_limit")
                if _PIL_FORMATS.get(im.format or "") != claimed_type:
                    raise PhotoValidationError("photo_type_mismatch")
                im.load()  # validate the full payload; truncated/corrupt pixel data fails here
    except PhotoValidationError:
        raise
    except (
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
    ) as exc:
        raise PhotoValidationError("photo_decode_failed") from exc
    return PhotoInfo(digest, claimed_type, len(data), width, height)


def expected_object_ref(bucket: str, tenant_id: str, pin_id: str, sha256: str) -> str:
    """The only ``object_ref`` a row for (tenant, pin, sha256) may hold in ``bucket``."""
    if not bucket:
        raise PhotoValidationError("photo_bucket_unconfigured")
    return f"s3://{bucket}/{media_key(tenant_id, pin_id, sha256)}"


def owned_object_ref(row: Mapping[str, Any], bucket: str, tenant_id: str, pin_id: str) -> str:
    """Return the row's ``object_ref`` only if it is the server-derived ref for this row.

    A poisoned row or a historical bug must not let the media service HEAD or presign an
    object outside this tenant + pin + digest namespace, nor in another bucket.
    """
    try:
        expected = expected_object_ref(
            bucket, tenant_id, pin_id, str(row["content_sha256"]).strip()
        )
    except (KeyError, TypeError, PhotoValidationError):
        raise PhotoValidationError("scout_photo_reference_invalid") from None
    if row.get("object_ref") != expected:
        raise PhotoValidationError("scout_photo_reference_invalid")
    return expected


def stored_sha(row: Mapping[str, Any]) -> str:
    return str(row["content_sha256"]).strip()


def public_receipt(row: Mapping[str, Any]) -> dict[str, Any]:
    """What a client may see of a stored row: never ``object_ref`` or the uploader."""
    return {
        "evidence_id": str(row["evidence_id"]),
        "field_id": row["field_id"],
        "pin_id": row["pin_id"],
        "sha256": stored_sha(row),
        "content_type": row["mime_type"],
        "size_bytes": row["size_bytes"],
        "width": row["image_width"],
        "height": row["image_height"],
        "persisted": True,
        "verification_state": "bytes_verified",
        "review_state": "unreviewed",
    }
