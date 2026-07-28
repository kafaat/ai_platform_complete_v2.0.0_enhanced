from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from core.crop_cards.loader import (
    load_crop_card,
    load_variety_card,
    validate_crop_card,
    validate_variety_card,
)
from core.knowledge_levels import fuse_confidence

_SCHEMA = "crop_knowledge_snapshot.v1"
_LAYER_VERSION = "crop-knowledge/1.0.0"
_ALLOWED_ANNOTATION_KINDS = {"regional", "field", "community"}
_ALLOWED_SOURCE_TYPES = {
    "fao56",
    "maas_hoffman",
    "ecocrop",
    "ngrc",
    "field_sensor",
    "farmer",
    "district_baseline",
}


@dataclass(frozen=True)
class KnowledgeAnnotation:
    annotation_id: str
    kind: str
    payload: dict[str, Any]
    source_type: str
    source_id: str
    version: str
    verified: bool = False


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _collect_card_sources(card: dict[str, Any]) -> list[str]:
    sources: list[str] = []
    for key in ("kc", "salinity", "thermal", "phenology"):
        block = card.get(key)
        if isinstance(block, dict) and block.get("source"):
            sources.append(str(block["source"]))
    return list(dict.fromkeys(sources))


def _validate_annotations(items: Iterable[KnowledgeAnnotation]) -> tuple[KnowledgeAnnotation, ...]:
    annotations = tuple(items)
    ids = [a.annotation_id for a in annotations]
    duplicates = sorted({x for x in ids if ids.count(x) > 1})
    if duplicates:
        raise ValueError(f"duplicate knowledge annotation ids: {duplicates}")
    for item in annotations:
        if not item.annotation_id or not item.version or not item.source_id:
            raise ValueError("annotation_id, version and source_id are required")
        if item.kind not in _ALLOWED_ANNOTATION_KINDS:
            raise ValueError(f"unsupported knowledge annotation kind: {item.kind}")
        if item.source_type not in _ALLOWED_SOURCE_TYPES:
            raise ValueError(f"unsupported knowledge source type: {item.source_type}")
        if item.kind in {"regional", "field"} and not item.verified:
            raise ValueError(f"unverified {item.kind} annotation cannot enter governed knowledge")
    return annotations


def build_crop_knowledge_snapshot(
    *,
    crop_id: str,
    variety_id: str | None = None,
    annotations: Iterable[KnowledgeAnnotation] = (),
) -> dict[str, Any]:
    card = load_crop_card(crop_id)
    if card is None:
        raise ValueError(f"unknown crop knowledge card: {crop_id}")
    validation = validate_crop_card(card)
    if not validation["valid"]:
        raise ValueError(f"invalid crop knowledge card {crop_id}: {validation['errors']}")

    variety = None
    if variety_id:
        variety = load_variety_card(variety_id)
        if variety is None:
            raise ValueError(f"unknown variety knowledge card: {variety_id}")
        validation = validate_variety_card(variety)
        if not validation["valid"]:
            raise ValueError(f"invalid variety knowledge card {variety_id}: {validation['errors']}")
        if variety.get("parent_crop_id") != crop_id:
            raise ValueError("variety parent crop does not match requested crop")

    governed_annotations = _validate_annotations(annotations)
    source_types = ["fao56", "maas_hoffman"]
    source_ids = [f"crop-card:{crop_id}"]
    source_ids.extend(f"source:{s}" for s in _collect_card_sources(card))
    if variety:
        source_ids.append(f"variety-card:{variety_id}")
    for item in governed_annotations:
        source_types.append(item.source_type)
        source_ids.append(f"knowledge:{item.source_id}@{item.version}")

    confidence, confidence_reason = fuse_confidence(source_types, proposed="high")
    payload = {
        "schema": _SCHEMA,
        "layer_version": _LAYER_VERSION,
        "crop_id": crop_id,
        "variety_id": variety_id,
        "core": {
            "identity": {k: card.get(k) for k in ("crop_id", "name_ar", "name_en", "crop_family")},
            "kc": card.get("kc"),
            "salinity": card.get("salinity"),
            "thermal": card.get("thermal"),
            "governing": card.get("governing"),
            "modifying": card.get("modifying"),
            "phenology": card.get("phenology"),
        },
        "variety": variety,
        "annotations": [
            {
                "annotation_id": a.annotation_id,
                "kind": a.kind,
                "payload": a.payload,
                "source_type": a.source_type,
                "source_id": a.source_id,
                "version": a.version,
                "verified": a.verified,
            }
            for a in governed_annotations
        ],
        "source_ids": list(dict.fromkeys(source_ids)),
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "decision_boundary": {
            "is_decision": False,
            "local_annotations_may_modify_not_override_governing": True,
            "consumer": "crop-intelligence-engine",
        },
    }
    payload["knowledge_digest"] = _digest(payload)
    return payload


def resolve_thermal_knowledge(snapshot: dict[str, Any]) -> dict[str, Any]:
    if snapshot.get("schema") != _SCHEMA:
        raise ValueError("crop knowledge snapshot is not canonical")
    thermal = (snapshot.get("core") or {}).get("thermal") or {}
    return {
        "gdd_base_c": thermal.get("gdd_base_c"),
        "gdd_to_maturity": thermal.get("gdd_to_maturity"),
        "source_ids": snapshot.get("source_ids") or [],
        "knowledge_digest": snapshot.get("knowledge_digest"),
    }
