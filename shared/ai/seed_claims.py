"""Claim-level provenance for seeded reference excerpts, including pre-metadata records."""

# Stable, reserved chunk IDs in the archived seed set; older indexes predate claim provenance.
UNREVIEWED_SEED_IDS = tuple(f"seed:{number}" for number in range(100, 154))


def seed_claim_details(metadata):
    """An ingestion manifest establishes document identity, not verification of an individual claim."""
    if not isinstance(metadata, dict):
        return {}
    chunk_id = metadata.get("chunk_id")
    document_id = metadata.get("document_id")
    if isinstance(document_id, str) and document_id.startswith("reference:"):
        document_seed_id = "seed:" + document_id.rsplit(":", 1)[-1]
        if document_seed_id in UNREVIEWED_SEED_IDS:
            chunk_id = document_seed_id
    if (
        chunk_id not in UNREVIEWED_SEED_IDS
        and metadata.get("claim_verification") != "not_verified_against_original"
    ):
        return {}
    label = metadata.get("claim_source_label")
    if not label and isinstance(document_id, str) and document_id.startswith("reference:"):
        label = document_id.removeprefix("reference:").rsplit(":", 1)[0]
    return {
        "claim_verification": "not_verified_against_original",
        "claim_source_label": label,
        "claim_locator": metadata.get("claim_locator"),
    }


_POINTER_KEYS = (
    "document_id",
    "source_type",
    "publisher",
    "source_uri",
    "source_revision",
    "page",
    "section",
)


def partition_generation_references(
    items, *, crop=None, region=None, jurisdiction=None, as_of=None, approvals=None
):
    """Admit an excerpt to the LLM context only on a matching approval record.

    ``approvals`` comes from ``reference_approvals.index_approvals``; by default it is the
    manifest shipped with this build. Every other excerpt is returned as a source pointer
    without its text. A flagged seed claim stays held even when a record names it.
    """
    from shared.ai.reference_approvals import (
        content_digest,
        excerpt_text,
        generation_hold_reason,
        shipped_approvals,
    )

    if approvals is None:
        approvals = shipped_approvals()
    usable, unreviewed = [], []
    for item in items:
        if not isinstance(item, dict):
            unreviewed.append(
                {"chunk_id": None, "generation_hold_reason": "excerpt_is_not_an_object"}
            )
            continue
        claim = seed_claim_details(item)
        reason = (
            "seed_claim_not_verified_against_original"
            if claim
            else generation_hold_reason(
                item,
                approvals,
                crop=crop,
                region=region,
                jurisdiction=jurisdiction,
                as_of=as_of,
            )
        )
        if reason is None:
            usable.append(item)
            continue
        text = excerpt_text(item)
        pointer = {key: item[key] for key in _POINTER_KEYS if item.get(key) is not None}
        if text is not None:
            pointer["content_digest"] = content_digest(text)
        unreviewed.append(
            {"chunk_id": item.get("chunk_id"), **pointer, **claim, "generation_hold_reason": reason}
        )
    return usable, unreviewed
