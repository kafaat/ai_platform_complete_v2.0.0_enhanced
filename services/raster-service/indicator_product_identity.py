"""Deterministic identity and batching plan for observed indicator products."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductIdentity:
    tenant_id: str
    field_geometry_hash: str
    scene_id: str
    indicator: str
    algorithm_version: str
    qa_mask_version: str | None

    def key(self) -> str:
        raw = json.dumps(
            {
                "tenant_id": self.tenant_id,
                "field_geometry_hash": self.field_geometry_hash,
                "scene_id": self.scene_id,
                "indicator": self.indicator.lower(),
                "algorithm_version": self.algorithm_version,
                "qa_mask_version": self.qa_mask_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "rip_" + hashlib.sha256(raw.encode()).hexdigest()


def plan_multi_indicator_batch(
    *,
    tenant_id: str,
    field_geometry_hash: str,
    scene_id: str,
    indicators: Iterable[str],
    algorithm_version: str,
    qa_mask_version: str | None,
) -> list[ProductIdentity]:
    seen = set()
    out = []
    for indicator in indicators:
        key = str(indicator).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            ProductIdentity(
                tenant_id, field_geometry_hash, scene_id, key, algorithm_version, qa_mask_version
            )
        )
    return out
