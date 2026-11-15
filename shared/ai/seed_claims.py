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


def partition_generation_references(items):
    """Separate auditable source pointers from excerpts allowed into the LLM context."""
    usable, unreviewed = [], []
    for item in items:
        claim = seed_claim_details(item)
        if claim:
            unreviewed.append({"chunk_id": item.get("chunk_id"), **claim})
        else:
            usable.append(item)
    return usable, unreviewed
