"""shared/memory/export_engine.py — SAHOOL Farm Memory: export engine.

Supports exporting farm memory to:
- JSON (always available)
- Parquet (requires pyarrow; raises OptionalDependencyError if missing)
- Portable JSON snapshots of scalar memory. Native Qdrant vector snapshots are
  rejected until a live collection exporter is configured; vectors are never
  silently represented as an empty list.
- Encrypted tarball AES-256 (always available via cryptography)

All operations are logged for audit trail.
Arabic error messages included for missing optional dependencies.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .models import SCHEMA_VERSION

if TYPE_CHECKING:
    from .farm_memory import FarmMemory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

EXPORT_FORMAT_VERSION = "1.0"
_SALT_LEN = 16
_ITER_COUNT = 200_000
_NONCE_LEN = 12


class OptionalDependencyError(ImportError):
    """رفع هذا الخطأ عند غياب اعتمادية اختيارية مطلوبة للتصدير.

    Raised when an optional dependency required for a specific export format
    is not installed.  Arabic message is included for farmer-facing tooling.
    """


class VectorExportUnavailable(RuntimeError):
    """Raised when a caller requests vectors without a real Qdrant exporter."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string with Z suffix."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _derive_key(password: str | bytes, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from password using PBKDF2-HMAC-SHA256."""
    if isinstance(password, str):
        password = password.encode("utf-8")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_ITER_COUNT,
    )
    return kdf.derive(password)


def generate_checksum(path: str | Path) -> str:
    """Compute SHA-256 hex digest of the file at ``path``.

    Parameters
    ----------
    path:
        Path to the file to checksum.

    Returns
    -------
    str
        Lowercase hex SHA-256 of the file bytes.
    """
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    digest = h.hexdigest()
    logger.info("export_engine: checksum(%s) = %s", path.name, digest)
    return digest


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------


def export_to_json(
    farm_id: str,
    path: str | Path,
    memory: FarmMemory,
    include_vectors: bool = False,
) -> dict[str, Any]:
    """Export farm memory to a JSON file.

    File structure:
    {
        "farm_id": "...",
        "export_version": "1.0",
        "exported_at": "2026-...",
        "schema_version": "v2",
        "conversations": [...],
        "preferences": {...},
        "patterns": [...],
        "recommendations": [...],
        "vector_export": {"included": false, "reason": "not_requested"}
    }

    Parameters
    ----------
    farm_id:
        Tenant identifier (validated against memory.farm_id).
    path:
        Destination file path (.json).
    memory:
        FarmMemory instance to export.
    include_vectors:
        Vector export is not implemented by this scalar JSON exporter. Passing
        True fails closed instead of producing a misleading empty list.

    Returns
    -------
    dict
        Manifest describing the export: path, checksum, item counts.
    """
    if memory.farm_id != farm_id:
        raise ValueError(
            f"Tenant isolation violation: memory.farm_id={memory.farm_id!r} != "
            f"export farm_id={farm_id!r}"
        )
    if include_vectors:
        raise VectorExportUnavailable(
            "Vector export requires a live, tenant-scoped Qdrant collection exporter; "
            "refusing to write a scalar-only backup that claims to contain vectors"
        )

    path = Path(path)
    raw = memory.raw_data()
    exported_at = _now_iso()

    payload: dict[str, Any] = {
        "farm_id": farm_id,
        "export_version": EXPORT_FORMAT_VERSION,
        "exported_at": exported_at,
        "schema_version": SCHEMA_VERSION,
        "conversations": raw.get("conversations", []),
        "preferences": raw.get("preferences", {}),
        "patterns": raw.get("patterns", []),
        "recommendations": raw.get("recommendations", []),
        "vector_export": {"included": False, "reason": "not_requested"},
    }

    # Atomic write: write to temp then rename
    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    checksum = generate_checksum(path)
    manifest = {
        "farm_id": farm_id,
        "format": "json",
        "path": str(path),
        "exported_at": exported_at,
        "schema_version": SCHEMA_VERSION,
        "checksum_sha256": checksum,
        "counts": {
            "conversations": len(payload["conversations"]),
            "patterns": len(payload["patterns"]),
            "recommendations": len(payload["recommendations"]),
            "preferences": len(payload["preferences"]),
        },
        "vectors_included": False,
    }
    logger.info(
        "export_engine[%s]: exported JSON → %s (conversations=%d, patterns=%d, "
        "recommendations=%d, prefs=%d)",
        farm_id,
        path,
        manifest["counts"]["conversations"],
        manifest["counts"]["patterns"],
        manifest["counts"]["recommendations"],
        manifest["counts"]["preferences"],
    )
    return manifest


# ---------------------------------------------------------------------------
# Parquet export (optional)
# ---------------------------------------------------------------------------


def export_to_parquet(
    farm_id: str,
    path: str | Path,
    memory: FarmMemory,
) -> dict[str, Any]:
    """Export farm memory to a Parquet file (requires pyarrow).

    Raises
    ------
    OptionalDependencyError
        If pyarrow is not installed.
        رسالة عربية: مكتبة pyarrow غير مثبّتة — الرجاء تثبيتها: pip install pyarrow
    """
    try:
        import pyarrow as pa  # noqa: F401
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise OptionalDependencyError(
            "مكتبة pyarrow غير مثبّتة — الرجاء تثبيتها لاستخدام تصدير Parquet: pip install pyarrow"
        ) from exc

    if memory.farm_id != farm_id:
        raise ValueError(
            f"Tenant isolation violation: memory.farm_id={memory.farm_id!r} != "
            f"export farm_id={farm_id!r}"
        )

    path = Path(path)
    raw = memory.raw_data()

    # Flatten conversations
    rows: list[dict[str, Any]] = []
    for conv in raw.get("conversations", []):
        rows.append(
            {
                "farm_id": farm_id,
                "kind": "conversation",
                "id": conv.get("id", ""),
                "text": f"{conv.get('user_query', '')} {conv.get('ai_response', '')}",
                "timestamp": str(conv.get("timestamp", "")),
                "topic": str(conv.get("topic", "")),
                "extra": json.dumps(conv, ensure_ascii=False),
            }
        )
    for pat in raw.get("patterns", []):
        rows.append(
            {
                "farm_id": farm_id,
                "kind": "pattern",
                "id": pat.get("id", ""),
                "text": pat.get("description", ""),
                "timestamp": str(pat.get("last_seen", "")),
                "topic": "",
                "extra": json.dumps(pat, ensure_ascii=False),
            }
        )
    for rec in raw.get("recommendations", []):
        rows.append(
            {
                "farm_id": farm_id,
                "kind": "recommendation",
                "id": rec.get("id", ""),
                "text": rec.get("text", ""),
                "timestamp": str(rec.get("made_at", "")),
                "topic": "",
                "extra": json.dumps(rec, ensure_ascii=False),
            }
        )

    import pyarrow as pa

    table = pa.table(
        {
            "farm_id": pa.array([r["farm_id"] for r in rows], type=pa.string()),
            "kind": pa.array([r["kind"] for r in rows], type=pa.string()),
            "id": pa.array([r["id"] for r in rows], type=pa.string()),
            "text": pa.array([r["text"] for r in rows], type=pa.string()),
            "timestamp": pa.array([r["timestamp"] for r in rows], type=pa.string()),
            "topic": pa.array([r["topic"] for r in rows], type=pa.string()),
            "extra": pa.array([r["extra"] for r in rows], type=pa.string()),
        }
    )
    pq.write_table(table, str(path))

    checksum = generate_checksum(path)
    exported_at = _now_iso()
    manifest = {
        "farm_id": farm_id,
        "format": "parquet",
        "path": str(path),
        "exported_at": exported_at,
        "schema_version": SCHEMA_VERSION,
        "checksum_sha256": checksum,
        "row_count": len(rows),
    }
    logger.info("export_engine[%s]: exported Parquet → %s (%d rows)", farm_id, path, len(rows))
    return manifest


# ---------------------------------------------------------------------------
# Qdrant snapshot (lazy; falls back to JSON snapshot)
# ---------------------------------------------------------------------------


def export_to_qdrant_snapshot(
    farm_id: str,
    path: str | Path,
    memory: FarmMemory,
) -> dict[str, Any]:
    """Export farm memory as a Qdrant collection snapshot (or JSON fallback).

    If ``qdrant_client`` is not installed, falls back to writing a portable
    JSON snapshot file and notes ``fallback_used: true`` in the manifest.

    Parameters
    ----------
    farm_id:
        Tenant identifier.
    path:
        Destination path (.snapshot or .json).
    memory:
        FarmMemory instance to export.

    Returns
    -------
    dict
        Manifest with ``fallback_used`` key indicating whether the JSON
        fallback was used.
    """
    if memory.farm_id != farm_id:
        raise ValueError(
            f"Tenant isolation violation: memory.farm_id={memory.farm_id!r} != "
            f"export farm_id={farm_id!r}"
        )

    path = Path(path)
    fallback_used = False

    try:
        import qdrant_client  # noqa: F401

        logger.info(
            "export_engine[%s]: qdrant_client available but snapshot export "
            "requires a live Qdrant instance — using JSON snapshot fallback",
            farm_id,
        )
        fallback_used = True
    except ImportError:
        logger.warning(
            "export_engine[%s]: qdrant_client غير مثبّت — استخدام JSON snapshot كبديل محمول",
            farm_id,
        )
        fallback_used = True

    # Write portable JSON snapshot
    raw = memory.raw_data()
    exported_at = _now_iso()
    snapshot: dict[str, Any] = {
        "format": "qdrant_snapshot_fallback",
        "farm_id": farm_id,
        "exported_at": exported_at,
        "schema_version": SCHEMA_VERSION,
        "collection_name": f"farm_{farm_id}",
        "data": raw,
    }
    snapshot_path = path.with_suffix(".json") if path.suffix == ".snapshot" else path
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, default=str, indent=2),
        encoding="utf-8",
    )

    checksum = generate_checksum(snapshot_path)
    manifest = {
        "farm_id": farm_id,
        "format": "qdrant_snapshot",
        "path": str(snapshot_path),
        "exported_at": exported_at,
        "schema_version": SCHEMA_VERSION,
        "checksum_sha256": checksum,
        "fallback_used": fallback_used,
        "note": (
            "qdrant_client غير مثبّت أو لا توجد خادم Qdrant — تم التصدير إلى JSON snapshot محمول"
            if fallback_used
            else "exported via qdrant"
        ),
    }
    logger.info(
        "export_engine[%s]: qdrant snapshot (fallback=%s) → %s",
        farm_id,
        fallback_used,
        snapshot_path,
    )
    return manifest


# ---------------------------------------------------------------------------
# Encrypted tarball export (AES-256-GCM + PBKDF2)
# ---------------------------------------------------------------------------


def export_to_encrypted_tarball(
    farm_id: str,
    path: str | Path,
    password: str | bytes,
    memory: FarmMemory,
) -> dict[str, Any]:
    """Export farm memory to an AES-256-GCM encrypted tarball.

    Steps:
    1. Export memory to JSON (in temp dir).
    2. Write manifest.json (checksum + schema_version + exported_at).
    3. Pack both into a .tar.gz.
    4. Derive AES-256 key from password via PBKDF2-HMAC-SHA256.
    5. Encrypt the tarball bytes with AESGCM; prepend ``salt || nonce``.
    6. Write a single ``.enc`` file atomically.

    File layout of the .enc file:
        [16 bytes salt] [12 bytes nonce] [ciphertext + 16-byte GCM tag]

    Parameters
    ----------
    farm_id:
        Tenant identifier.
    path:
        Destination path for the ``.enc`` file.
    password:
        Encryption password (str or bytes). Not stored anywhere.
    memory:
        FarmMemory instance to export.

    Returns
    -------
    dict
        Manifest including checksum, exported_at, and schema_version.
    """
    if memory.farm_id != farm_id:
        raise ValueError(
            f"Tenant isolation violation: memory.farm_id={memory.farm_id!r} != "
            f"export farm_id={farm_id!r}"
        )

    path = Path(path)
    exported_at = _now_iso()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Step 1: Export JSON
        json_path = tmp / "memory.json"
        json_manifest = export_to_json(farm_id, json_path, memory, include_vectors=False)
        json_checksum = json_manifest["checksum_sha256"]

        # Step 2: Write manifest.json
        manifest_data: dict[str, Any] = {
            "farm_id": farm_id,
            "export_version": EXPORT_FORMAT_VERSION,
            "exported_at": exported_at,
            "schema_version": SCHEMA_VERSION,
            "json_checksum_sha256": json_checksum,
            "counts": json_manifest["counts"],
            "vectors_included": False,
        }
        manifest_path = tmp / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Step 3: Create tar.gz
        tarball_path = tmp / "memory.tar.gz"
        with tarfile.open(tarball_path, "w:gz") as tar:
            tar.add(json_path, arcname="memory.json")
            tar.add(manifest_path, arcname="manifest.json")

        tarball_bytes = tarball_path.read_bytes()

        # Step 4 & 5: Derive key and encrypt
        salt = os.urandom(_SALT_LEN)
        nonce = os.urandom(_NONCE_LEN)
        key = _derive_key(password, salt)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, tarball_bytes, None)

        # File layout: [salt 16B][nonce 12B][ciphertext]
        enc_bytes = salt + nonce + ciphertext

        # Step 6: Atomic write
        tmp_enc = path.with_suffix(".enc.tmp")
        try:
            tmp_enc.write_bytes(enc_bytes)
            tmp_enc.replace(path)
        except Exception:
            tmp_enc.unlink(missing_ok=True)
            raise

    checksum = generate_checksum(path)
    final_manifest: dict[str, Any] = {
        "farm_id": farm_id,
        "format": "encrypted_tarball",
        "path": str(path),
        "exported_at": exported_at,
        "schema_version": SCHEMA_VERSION,
        "checksum_sha256": checksum,
        "json_checksum_sha256": json_checksum,
        "counts": json_manifest["counts"],
        "encryption": "AES-256-GCM",
        "kdf": f"PBKDF2-HMAC-SHA256 ({_ITER_COUNT} iterations)",
    }
    logger.info(
        "export_engine[%s]: encrypted tarball → %s (size=%d bytes)",
        farm_id,
        path,
        len(enc_bytes),
    )
    return final_manifest


# ---------------------------------------------------------------------------
# Decrypt helper (used by import_engine)
# ---------------------------------------------------------------------------


def _decrypt_tarball(enc_path: Path, password: str | bytes) -> bytes:
    """Decrypt an encrypted tarball produced by ``export_to_encrypted_tarball``.

    Parameters
    ----------
    enc_path:
        Path to the ``.enc`` file.
    password:
        Decryption password.

    Returns
    -------
    bytes
        Raw tar.gz bytes.

    Raises
    ------
    ValueError
        If decryption fails (wrong password or corrupted file).
    """
    enc_bytes = enc_path.read_bytes()
    if len(enc_bytes) < _SALT_LEN + _NONCE_LEN + 16:
        raise ValueError(
            f"الملف المشفّر تالف أو قصير جدّاً: {enc_path.name} (size={len(enc_bytes)} bytes)"
        )

    salt = enc_bytes[:_SALT_LEN]
    nonce = enc_bytes[_SALT_LEN : _SALT_LEN + _NONCE_LEN]
    ciphertext = enc_bytes[_SALT_LEN + _NONCE_LEN :]

    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise ValueError("فشل فك تشفير الملف — تحقّق من صحة كلمة المرور أو سلامة الملف.") from exc

    return plaintext
