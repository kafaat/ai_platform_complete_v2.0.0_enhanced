"""Approval manifest: the only way a reference excerpt becomes generation-eligible.

``reference_approvals.json`` beside this module holds one record per approved excerpt:

    {
      "approval_id": "unique id",
      "content_digest": "sha256 hex of the exact excerpt text (UTF-8)",
      "source_revision": "revision of the source the excerpt was read from",
      "source": {"title": "...", "publisher": "...", "publication_date": "YYYY-MM-DD"},
      "reviewer": {"name": "...", "identity": "registration number or institutional address"},
      "reviewed_on": "YYYY-MM-DD",
      "valid_until": "YYYY-MM-DD",
      "applicability": {"crops": ["..."], "regions": ["..."], "jurisdiction": "..."}
    }

Every field above is mandatory; ``source`` may also carry ``source_uri`` and ``locator``.
There is no wildcard: crops and regions are listed one by one. A record approves one
digest at one source revision, so edited text or a new revision needs a new review.
An approval admits text into the model context only. It grants no decision authority.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

MANIFEST_SCHEMA = "sahool.reference_approval_manifest"
MANIFEST_SCHEMA_VERSION = 1
MANIFEST_PATH = Path(__file__).with_name("reference_approvals.json")

_DIGEST = re.compile(r"[0-9a-f]{64}")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TOP_KEYS = {"schema", "schema_version", "approvals"}
_RECORD_KEYS = {
    "approval_id",
    "content_digest",
    "source_revision",
    "source",
    "reviewer",
    "reviewed_on",
    "valid_until",
    "applicability",
}
_SOURCE_REQUIRED = ("title", "publisher", "publication_date")
_SOURCE_KEYS = {*_SOURCE_REQUIRED, "source_uri", "locator"}
_REVIEWER_KEYS = {"name", "identity"}
_APPLICABILITY_KEYS = {"crops", "regions", "jurisdiction"}


class ApprovalManifestError(ValueError):
    """The manifest is rejected as a whole; no record of it is honoured."""


def content_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_scope(value) -> str:
    """Comparison form of a crop, region or jurisdiction name; empty when unusable."""
    if not isinstance(value, str):
        return ""
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _named(value) -> bool:
    """A real name has a letter or digit, so "*" and blanks are never a scope."""
    return isinstance(value, str) and any(ch.isalnum() for ch in value)


def _parse_date(value) -> date | None:
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _object_errors(value, where: str, required, allowed) -> list[str]:
    if not isinstance(value, dict):
        return [f"{where} must be an object"]
    errors = [f"{where}.{key} is not a known field" for key in sorted(set(value) - set(allowed))]
    errors += [f"{where}.{key} is required" for key in required if key not in value]
    return errors


def _record_errors(record, where: str) -> list[str]:
    errors = _object_errors(record, where, sorted(_RECORD_KEYS), _RECORD_KEYS)
    if errors:
        return errors
    if not _named(record["approval_id"]):
        errors.append(f"{where}.approval_id must be a non-empty string")
    digest = record["content_digest"]
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        errors.append(f"{where}.content_digest must be 64 lowercase hex characters")
    if not _named(record["source_revision"]):
        errors.append(f"{where}.source_revision must be a non-empty string")

    source = record["source"]
    source_errors = _object_errors(source, f"{where}.source", _SOURCE_REQUIRED, _SOURCE_KEYS)
    errors += source_errors
    published = None
    if not source_errors:
        errors += [
            f"{where}.source.{key} must be a non-empty string"
            for key in sorted(set(source) - {"publication_date"})
            if not _named(source[key])
        ]
        published = _parse_date(source["publication_date"])
        if published is None:
            errors.append(f"{where}.source.publication_date must be a YYYY-MM-DD date")

    reviewer = record["reviewer"]
    reviewer_errors = _object_errors(
        reviewer, f"{where}.reviewer", sorted(_REVIEWER_KEYS), _REVIEWER_KEYS
    )
    errors += reviewer_errors
    if not reviewer_errors:
        errors += [
            f"{where}.reviewer.{key} must be a non-empty string"
            for key in sorted(_REVIEWER_KEYS)
            if not _named(reviewer[key])
        ]

    reviewed = _parse_date(record["reviewed_on"])
    valid_until = _parse_date(record["valid_until"])
    if reviewed is None:
        errors.append(f"{where}.reviewed_on must be a YYYY-MM-DD date")
    if valid_until is None:
        errors.append(f"{where}.valid_until must be a YYYY-MM-DD date")
    if reviewed and valid_until and valid_until < reviewed:
        errors.append(f"{where}.valid_until is before reviewed_on")
    if reviewed and published and published > reviewed:
        errors.append(f"{where}.source.publication_date is after reviewed_on")

    scope = record["applicability"]
    scope_errors = _object_errors(
        scope, f"{where}.applicability", sorted(_APPLICABILITY_KEYS), _APPLICABILITY_KEYS
    )
    errors += scope_errors
    if not scope_errors:
        for key in ("crops", "regions"):
            names = scope[key]
            if not isinstance(names, list) or not names or not all(_named(n) for n in names):
                errors.append(f"{where}.applicability.{key} must be a non-empty list of names")
        if not _named(scope["jurisdiction"]):
            errors.append(f"{where}.applicability.jurisdiction must be a non-empty string")
    return errors


def validate_manifest(manifest) -> list[str]:
    """Return every reason the manifest is unusable; an empty list means it is valid."""
    errors = _object_errors(manifest, "manifest", sorted(_TOP_KEYS), _TOP_KEYS)
    if errors:
        return errors
    if manifest["schema"] != MANIFEST_SCHEMA:
        errors.append(f"manifest.schema must be {MANIFEST_SCHEMA!r}")
    version = manifest["schema_version"]
    if type(version) is not int or version != MANIFEST_SCHEMA_VERSION:
        errors.append(f"manifest.schema_version must be {MANIFEST_SCHEMA_VERSION}")
    approvals = manifest["approvals"]
    if not isinstance(approvals, list):
        return [*errors, "manifest.approvals must be a list"]
    seen_ids: set[str] = set()
    seen_targets: set[tuple[str, str]] = set()
    for index, record in enumerate(approvals):
        where = f"approvals[{index}]"
        record_errors = _record_errors(record, where)
        errors += record_errors
        if record_errors:
            continue
        if record["approval_id"] in seen_ids:
            errors.append(f"{where}.approval_id is used more than once")
        seen_ids.add(record["approval_id"])
        target = (record["content_digest"], record["source_revision"])
        if target in seen_targets:
            errors.append(f"{where} approves a digest and revision that already has a record")
        seen_targets.add(target)
    return errors


def index_approvals(manifest) -> dict[tuple[str, str], dict]:
    """Validate, then key the records by (content digest, source revision)."""
    errors = validate_manifest(manifest)
    if errors:
        raise ApprovalManifestError("; ".join(errors))
    return {
        (record["content_digest"], record["source_revision"]): record
        for record in manifest["approvals"]
    }


def load_manifest(path: Path | str | None = None):
    target = Path(path) if path is not None else MANIFEST_PATH
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ApprovalManifestError(f"approval manifest unreadable: {exc}") from exc


@lru_cache(maxsize=1)
def shipped_approvals() -> dict[tuple[str, str], dict] | None:
    """Approvals packaged with this build; ``None`` when the manifest is unusable."""
    try:
        return index_approvals(load_manifest())
    except ApprovalManifestError as exc:
        logger.error(
            "reference approval manifest rejected; nothing is generation-eligible: %s", exc
        )
        return None


def excerpt_text(item) -> str | None:
    """The text an excerpt would put into the model context."""
    for key in ("text", "content", "snippet"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def generation_hold_reason(
    item,
    approvals,
    *,
    crop=None,
    region=None,
    jurisdiction=None,
    as_of: date | None = None,
) -> str | None:
    """Why this excerpt stays out of generation; ``None`` only for an approved excerpt."""
    if approvals is None:
        return "approval_manifest_invalid"
    text = excerpt_text(item)
    if text is None:
        return "excerpt_has_no_text"
    digest = content_digest(text)
    declared = item.get("content_digest")
    if declared is not None and declared != digest:
        return "content_digest_mismatch"
    revision = item.get("source_revision")
    if not isinstance(revision, str) or not revision.strip():
        return "source_revision_missing"
    record = approvals.get((digest, revision))
    if record is None:
        return "no_approval_record"
    today = as_of or datetime.now(UTC).date()
    reviewed = _parse_date(record.get("reviewed_on"))
    valid_until = _parse_date(record.get("valid_until"))
    if reviewed is None or valid_until is None:
        return "approval_record_invalid"
    if today < reviewed:
        return "approval_not_yet_effective"
    if today > valid_until:
        return "approval_expired"
    scope = record.get("applicability")
    if not isinstance(scope, dict):
        return "approval_record_invalid"
    for asked, key, unknown, mismatch in (
        (crop, "crops", "question_crop_unknown", "crop_not_applicable"),
        (region, "regions", "question_region_unknown", "region_not_applicable"),
    ):
        wanted = normalize_scope(asked)
        if not wanted:
            return unknown
        names = scope.get(key)
        if not isinstance(names, list) or wanted not in {normalize_scope(n) for n in names}:
            return mismatch
    if jurisdiction is not None and normalize_scope(jurisdiction) != normalize_scope(
        scope.get("jurisdiction")
    ):
        return "jurisdiction_not_applicable"
    return None


def main(argv: list[str] | None = None) -> int:
    """Validate a manifest file: ``python -m shared.ai.reference_approvals [path]``."""
    import sys

    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else MANIFEST_PATH
    try:
        errors = validate_manifest(load_manifest(path))
    except ApprovalManifestError as exc:
        errors = [str(exc)]
    for error in errors:
        print(error)
    if not errors:
        print(f"{path}: valid")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
