"""Read-only crop reference for the field advisor; never tenant facts or decisions.

The field and season are read by their authoritative service. The global crop
cards are reference-only and cannot be changed by tenant-specific observations.
"""

from __future__ import annotations

from typing import Any

from core.crop_cards.loader import load_variety_card
from core.crop_intelligence.knowledge_layer import build_crop_knowledge_snapshot
from core.season_phenology import resolve_crop_id


def compose_advisor_crop_reference(
    field_profile: dict[str, Any] | None,
    active_season: dict[str, Any] | None,
) -> dict[str, Any]:
    """Bounded, cited crop knowledge selected only by owner-read crop identity."""
    profile = field_profile if isinstance(field_profile, dict) else {}
    season = active_season if isinstance(active_season, dict) else {}
    crops = season.get("crops")
    if isinstance(crops, list):
        candidates = [c.strip() for c in crops if isinstance(c, str) and c.strip()]
        if len(candidates) != 1:
            return {"status": "unavailable", "reason": "season_crop_ambiguous_or_missing"}
        declared = candidates[0]
    else:
        declared = season.get("crop") or profile.get("crop")
    if not isinstance(declared, str) or not declared.strip():
        return {"status": "unavailable", "reason": "crop_not_recorded"}
    crop_id = resolve_crop_id(declared.strip())
    if crop_id is None:
        return {"status": "unavailable", "reason": "crop_not_in_reference_catalog"}

    limitations: list[str] = []
    variety_id = None
    cultivar = season.get("cultivar")
    if isinstance(cultivar, str) and cultivar.strip():
        card = load_variety_card(cultivar.strip())
        if card and card.get("parent_crop_id") == crop_id:
            variety_id = cultivar.strip()
        else:
            limitations.append("season_variety_not_in_reference_catalog")
    try:
        snapshot = build_crop_knowledge_snapshot(crop_id=crop_id, variety_id=variety_id)
    except ValueError:
        return {"status": "unavailable", "reason": "governed_crop_card_invalid"}
    core = snapshot["core"]
    return {
        "status": "reference_only",
        "crop_id": crop_id,
        "variety_id": variety_id,
        "knowledge_digest": snapshot["knowledge_digest"],
        "source_ids": snapshot["source_ids"][:16],
        "confidence": snapshot["confidence"],
        "thermal": core.get("thermal"),
        "kc": core.get("kc"),
        "salinity": core.get("salinity"),
        "limitations": limitations,
        "decision_authority": "none",
    }
