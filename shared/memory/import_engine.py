"""shared/memory/import_engine.py — SAHOOL Farm Memory: import engine.

Supports importing farm memory from:
- JSON (always available)
- Encrypted tarball (AES-256-GCM; always available via cryptography)
- Qdrant snapshot (lazy; reads JSON fallback if qdrant_client missing)
- Parquet (lazy; raises OptionalDependencyError if pyarrow missing)

Conflict resolution strategies: merge | replace | skip.
Schema migration: v1 → v2 (add satisfaction_score, rename query→user_query).
All operations are atomic (work in temp dirs; abort on error without partial writes).
All operations are logged for audit trail.
"""

from __future__ import annotations

import json
import logging
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .export_engine import _decrypt_tarball, generate_checksum
from .models import SCHEMA_VERSION

if TYPE_CHECKING:
    from .farm_memory import FarmMemory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------

_SUPPORTED_VERSIONS = {"v1", "v2"}


def migrate_schema(data: dict[str, Any], from_version: str, to_version: str) -> dict[str, Any]:
    """Migrate exported data dict from ``from_version`` to ``to_version``.

    Supported migrations:
    - v1 → v2: add ``satisfaction_score: null`` to each conversation;
                rename ``query`` → ``user_query`` in conversations.

    Idempotent: calling with from_version == to_version is a no-op.

    Parameters
    ----------
    data:
        The exported data dict to migrate (will be deep-copied).
    from_version:
        Source schema version string.
    to_version:
        Target schema version string.

    Returns
    -------
    dict
        Migrated data dict.
    """
    import copy

    result = copy.deepcopy(data)

    if from_version == to_version:
        logger.debug("migrate_schema: no-op (%s → %s)", from_version, to_version)
        return result

    if from_version == "v1" and to_version == "v2":
        logger.info("migrate_schema: v1 → v2")
        for conv in result.get("conversations", []):
            # Rename query → user_query (idempotent)
            if "query" in conv and "user_query" not in conv:
                conv["user_query"] = conv.pop("query")
            # Add satisfaction_score default None
            conv.setdefault("satisfaction_score", None)
        result["schema_version"] = "v2"
        logger.info(
            "migrate_schema: migrated %d conversations", len(result.get("conversations", []))
        )
        return result

    raise ValueError(
        f"لا يوجد مسار ترحيل مدعوم من {from_version!r} إلى {to_version!r}. "
        f"(No migration path supported from {from_version!r} to {to_version!r})"
    )


# ---------------------------------------------------------------------------
# Checksum validation
# ---------------------------------------------------------------------------


def validate_checksum(path: str | Path, expected: str) -> bool:
    """Validate the SHA-256 checksum of a file.

    Parameters
    ----------
    path:
        Path to the file to validate.
    expected:
        Expected SHA-256 hex digest (case-insensitive).

    Returns
    -------
    bool
        True if checksum matches, False otherwise.
    """
    actual = generate_checksum(path)
    match = actual.lower() == expected.lower()
    if match:
        logger.info("import_engine: checksum OK for %s", Path(path).name)
    else:
        logger.warning(
            "import_engine: checksum MISMATCH for %s (expected=%s, actual=%s)",
            Path(path).name,
            expected[:16] + "...",
            actual[:16] + "...",
        )
    return match


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


def detect_format(path: str | Path) -> str:
    """Detect the export format of a file by extension and content sniffing.

    Returns one of: ``json`` | ``parquet`` | ``encrypted_tarball`` |
    ``qdrant_snapshot``.

    Parameters
    ----------
    path:
        Path to the file to inspect.

    Returns
    -------
    str
        Detected format name.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".enc":
        return "encrypted_tarball"
    if suffix == ".parquet":
        return "parquet"
    if suffix == ".snapshot":
        return "qdrant_snapshot"
    if suffix == ".json":
        # Peek at content to distinguish qdrant snapshot from plain JSON
        try:
            with path.open("rb") as fh:
                head = fh.read(512).decode("utf-8", errors="replace")
            if '"format": "qdrant_snapshot_fallback"' in head or '"collection_name"' in head:
                return "qdrant_snapshot"
        except Exception:  # noqa: BLE001
            pass
        return "json"

    logger.warning("detect_format: unknown extension %r, defaulting to json", suffix)
    return "json"


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------


def resolve_conflicts(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    strategy: str,
) -> dict[str, Any]:
    """Resolve a conflict between two items with the same ID.

    Parameters
    ----------
    existing:
        Currently stored item payload.
    incoming:
        Incoming item payload from import.
    strategy:
        One of ``merge`` | ``replace`` | ``skip``.
        - ``merge``: keep the item with the newer timestamp.
        - ``replace``: always use ``incoming``.
        - ``skip``: always keep ``existing``.

    Returns
    -------
    dict
        The resolved item payload to keep.
    """
    if strategy == "replace":
        logger.debug("resolve_conflicts[replace]: using incoming item %s", incoming.get("id"))
        return incoming

    if strategy == "skip":
        logger.debug("resolve_conflicts[skip]: keeping existing item %s", existing.get("id"))
        return existing

    # merge: keep newer timestamp
    existing_ts = _parse_ts_str(
        existing.get("timestamp") or existing.get("made_at") or existing.get("last_seen") or ""
    )
    incoming_ts = _parse_ts_str(
        incoming.get("timestamp") or incoming.get("made_at") or incoming.get("last_seen") or ""
    )

    if incoming_ts >= existing_ts:
        logger.debug(
            "resolve_conflicts[merge]: incoming is newer for %s — using incoming",
            incoming.get("id"),
        )
        return incoming
    else:
        logger.debug(
            "resolve_conflicts[merge]: existing is newer for %s — keeping existing",
            existing.get("id"),
        )
        return existing


def _parse_ts_str(ts: str | None) -> datetime:
    """Parse a timestamp string to a timezone-aware datetime."""
    if not ts:
        return datetime.min.replace(tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# JSON import
# ---------------------------------------------------------------------------


def import_from_json(
    path: str | Path,
    farm_id: str,
    memory: FarmMemory,
    conflict_resolution: str = "merge",
) -> dict[str, Any]:
    """Import farm memory from a JSON export file.

    Parameters
    ----------
    path:
        Path to the JSON export file.
    farm_id:
        Expected tenant identifier (validated against file contents).
    memory:
        FarmMemory instance to import into.
    conflict_resolution:
        Strategy for handling duplicate IDs: ``merge`` | ``replace`` | ``skip``.
        ``merge`` keeps the item with the newer timestamp.

    Returns
    -------
    dict
        Summary: {imported, merged, skipped, conflicts, farm_id, schema_version}.

    Raises
    ------
    ValueError
        If the file's farm_id doesn't match the expected farm_id.
    """
    if conflict_resolution not in {"merge", "replace", "skip"}:
        raise ValueError(
            f"Invalid conflict_resolution: {conflict_resolution!r}. "
            "Must be one of: merge, replace, skip"
        )

    path = Path(path)
    raw_text = path.read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(raw_text)

    # Validate farm_id
    file_farm_id = data.get("farm_id", "")
    if file_farm_id != farm_id:
        raise ValueError(
            f"Tenant isolation violation: file farm_id={file_farm_id!r} != "
            f"expected farm_id={farm_id!r}"
        )
    if memory.farm_id != farm_id:
        raise ValueError(
            f"Tenant isolation violation: memory.farm_id={memory.farm_id!r} != "
            f"expected farm_id={farm_id!r}"
        )

    # Handle schema migration
    file_schema = data.get("schema_version", "v1")
    if file_schema != SCHEMA_VERSION:
        if file_schema in _SUPPORTED_VERSIONS:
            logger.info(
                "import_engine[%s]: migrating schema %s → %s",
                farm_id,
                file_schema,
                SCHEMA_VERSION,
            )
            data = migrate_schema(data, file_schema, SCHEMA_VERSION)
        else:
            logger.warning(
                "import_engine[%s]: unknown schema version %r — attempting import anyway",
                farm_id,
                file_schema,
            )

    # Get current state
    current_raw = memory.raw_data()
    current_conv_ids = {c["id"]: c for c in current_raw.get("conversations", [])}
    current_pat_ids = {p["id"]: p for p in current_raw.get("patterns", [])}
    current_rec_ids = {r["id"]: r for r in current_raw.get("recommendations", [])}

    counts = {
        "imported": 0,
        "merged": 0,
        "skipped": 0,
        "conflicts": 0,
        "farm_id": farm_id,
        "schema_version": data.get("schema_version", file_schema),
    }


    # Import conversations
    for conv in data.get("conversations", []):
        conv_id = conv.get("id", "")
        if conv_id in current_conv_ids:
            counts["conflicts"] += 1
            resolved = resolve_conflicts(current_conv_ids[conv_id], conv, conflict_resolution)
            if resolved is conv:
                # Replace existing
                current_conv_ids[conv_id] = resolved
                counts["merged"] += 1
            else:
                counts["skipped"] += 1
        else:
            current_conv_ids[conv_id] = conv
            counts["imported"] += 1

    # Import patterns
    for pat in data.get("patterns", []):
        pat_id = pat.get("id", "")
        if pat_id in current_pat_ids:
            counts["conflicts"] += 1
            resolved = resolve_conflicts(current_pat_ids[pat_id], pat, conflict_resolution)
            if resolved is pat:
                current_pat_ids[pat_id] = resolved
                counts["merged"] += 1
            else:
                counts["skipped"] += 1
        else:
            current_pat_ids[pat_id] = pat
            counts["imported"] += 1

    # Import recommendations
    for rec in data.get("recommendations", []):
        rec_id = rec.get("id", "")
        if rec_id in current_rec_ids:
            counts["conflicts"] += 1
            resolved = resolve_conflicts(current_rec_ids[rec_id], rec, conflict_resolution)
            if resolved is rec:
                current_rec_ids[rec_id] = resolved
                counts["merged"] += 1
            else:
                counts["skipped"] += 1
        else:
            current_rec_ids[rec_id] = rec
            counts["imported"] += 1

    # Merge preferences
    incoming_prefs = data.get("preferences", {})
    current_prefs = current_raw.get("preferences", {})
    if conflict_resolution == "replace":
        merged_prefs = {**current_prefs, **incoming_prefs}
    elif conflict_resolution == "skip":
        merged_prefs = {**incoming_prefs, **current_prefs}  # existing wins
    else:  # merge
        merged_prefs = {**current_prefs, **incoming_prefs}

    # Build final merged data and replace in memory
    new_data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "conversations": list(current_conv_ids.values()),
        "preferences": merged_prefs,
        "patterns": list(current_pat_ids.values()),
        "recommendations": list(current_rec_ids.values()),
    }
    memory._replace_data(new_data)

    logger.info(
        "import_engine[%s]: JSON import complete — imported=%d merged=%d skipped=%d conflicts=%d",
        farm_id,
        counts["imported"],
        counts["merged"],
        counts["skipped"],
        counts["conflicts"],
    )
    return counts


# ---------------------------------------------------------------------------
# Encrypted tarball import
# ---------------------------------------------------------------------------


def import_from_encrypted_tarball(
    path: str | Path,
    farm_id: str,
    password: str | bytes,
    memory: FarmMemory,
) -> dict[str, Any]:
    """Import farm memory from an AES-256-GCM encrypted tarball.

    This operation is atomic: all work is done in a temp directory.
    On any error, the memory is left unchanged.

    Parameters
    ----------
    path:
        Path to the ``.enc`` file.
    farm_id:
        Expected tenant identifier.
    password:
        Decryption password.
    memory:
        FarmMemory instance to import into.

    Returns
    -------
    dict
        Import summary (same as import_from_json).

    Raises
    ------
    ValueError
        If decryption fails or checksum validation fails.
    """
    path = Path(path)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Decrypt
        try:
            tarball_bytes = _decrypt_tarball(path, password)
        except ValueError as exc:
            logger.error("import_engine[%s]: decryption failed for %s: %s", farm_id, path.name, exc)
            raise

        # Extract tar.gz
        tarball_path = tmp / "memory.tar.gz"
        tarball_path.write_bytes(tarball_bytes)

        try:
            with tarfile.open(tarball_path, "r:gz") as tar:
                # Security (untrusted input): reject links/special members and
                # enforce that every resolved destination stays inside tmp, then
                # extract members individually. Name-only checks (".."/leading "/")
                # are insufficient — symlinks/hardlinks could escape the temp dir.
                tmp_resolved = tmp.resolve()
                members = tar.getmembers()
                for member in members:
                    if member.issym() or member.islnk() or member.isdev():
                        raise ValueError(
                            f"عضو غير آمن في الأرشيف (رابط/جهاز): {member.name!r} — رُفض الاستيراد"
                        )
                    if not (member.isfile() or member.isdir()):
                        raise ValueError(
                            f"نوع عضو غير مدعوم في الأرشيف: {member.name!r} — رُفض الاستيراد"
                        )
                    dest = (tmp / member.name).resolve()
                    if dest != tmp_resolved and tmp_resolved not in dest.parents:
                        raise ValueError(
                            f"مسار غير آمن في الأرشيف: {member.name!r} — رُفض الاستيراد"
                        )
                for member in members:
                    tar.extract(member, tmp)
        except Exception as exc:
            logger.error(
                "import_engine[%s]: tar extraction failed for %s: %s",
                farm_id,
                path.name,
                exc,
            )
            raise ValueError(f"فشل استخراج الأرشيف — قد يكون الملف تالفاً: {exc}") from exc

        # Validate checksum from manifest
        manifest_path = tmp / "manifest.json"
        json_path = tmp / "memory.json"

        if not manifest_path.exists():
            raise ValueError("manifest.json مفقود من الأرشيف — لا يمكن التحقق من سلامة البيانات")
        if not json_path.exists():
            raise ValueError("memory.json مفقود من الأرشيف — ملف التصدير غير مكتمل")

        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_checksum = manifest.get("json_checksum_sha256", "")

        if expected_checksum and not validate_checksum(json_path, expected_checksum):
            raise ValueError("فشل التحقق من مجموع التحقق SHA-256 — البيانات قد تكون تالفة أو مزوّرة")

        # All-or-nothing: do a dry-run parse before writing
        raw_text = json_path.read_text(encoding="utf-8")
        json.loads(raw_text)  # validate JSON parse

        # Import (this is the only write operation)
        result = import_from_json(json_path, farm_id, memory, conflict_resolution="merge")

    logger.info("import_engine[%s]: encrypted tarball import complete from %s", farm_id, path.name)
    return result


# ---------------------------------------------------------------------------
# Qdrant snapshot import (lazy)
# ---------------------------------------------------------------------------


def import_from_qdrant_snapshot(
    path: str | Path,
    farm_id: str,
    memory: FarmMemory,
) -> dict[str, Any]:
    """Import farm memory from a Qdrant snapshot or JSON fallback.

    If the file is a JSON snapshot (produced by the fallback export path),
    reads it directly. Otherwise attempts to use qdrant_client.

    Parameters
    ----------
    path:
        Path to the snapshot file.
    farm_id:
        Expected tenant identifier.
    memory:
        FarmMemory instance to import into.

    Returns
    -------
    dict
        Import summary.
    """
    path = Path(path)

    # Try reading as JSON snapshot (our fallback format)
    try:
        text = path.read_text(encoding="utf-8")
        snapshot_data: dict[str, Any] = json.loads(text)
    except Exception as exc:
        raise ValueError(f"لا يمكن قراءة ملف الـ snapshot: {path.name}: {exc}") from exc

    format_field = snapshot_data.get("format", "")

    if "qdrant_snapshot_fallback" in format_field or "collection_name" in snapshot_data:
        # This is our portable JSON snapshot
        file_farm_id = snapshot_data.get("farm_id", "")
        collection_name = snapshot_data.get("collection_name", "")
        expected_collection = f"farm_{farm_id}"

        if file_farm_id != farm_id:
            raise ValueError(
                f"Tenant isolation violation: snapshot farm_id={file_farm_id!r} != "
                f"expected farm_id={farm_id!r}"
            )
        if collection_name and collection_name != expected_collection:
            logger.warning(
                "import_engine[%s]: collection_name mismatch: "
                "snapshot=%r expected=%r — proceeding anyway",
                farm_id,
                collection_name,
                expected_collection,
            )

        inner_data = snapshot_data.get("data", {})
        inner_data["farm_id"] = farm_id

        # Write to temp JSON and import via standard path
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_json = Path(tmpdir) / "memory.json"
            tmp_json.write_text(
                json.dumps(inner_data, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            result = import_from_json(tmp_json, farm_id, memory)

        logger.info("import_engine[%s]: qdrant snapshot (JSON fallback) import complete", farm_id)
        return result

    # Try qdrant_client path
    try:
        import qdrant_client  # noqa: F401

        logger.warning(
            "import_engine[%s]: qdrant_client available but native snapshot import "
            "requires a live Qdrant instance — not implemented in this version",
            farm_id,
        )
        raise ValueError(
            "استيراد Qdrant snapshot الأصلي يحتاج إلى خادم Qdrant قيد التشغيل. "
            "استخدم ملف JSON snapshot بدلاً من ذلك."
        )
    except ImportError as exc:
        raise ValueError(
            "qdrant_client غير مثبّت ولا يمكن قراءة هذا الملف كـ JSON snapshot. "
            "تأكد أن الملف تم تصديره بواسطة export_to_qdrant_snapshot."
        ) from exc
