#!/usr/bin/env python3
"""Read-only capability view resolved by the adjudicated field-authority policy.

This module is intentionally not a registry and writes no artifact.  It joins the
canonical capability definition with the legacy mutable projection at read time so
consumers can migrate field-by-field without creating a third source of truth.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs/capability-registry/field_authority_policy.json"
CANONICAL = ROOT / "docs/capability-registry/generated/capability_registry.json"
LEGACY = ROOT / "capabilities/registry/capabilities.json"
POLICY_SCHEMA = "sahool.capability-field-authority/v1"


class CapabilityAuthorityError(RuntimeError):
    """The authoritative capability view cannot be resolved unambiguously."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityAuthorityError(f"cannot read capability authority input: {path}") from exc
    if not isinstance(value, dict):
        raise CapabilityAuthorityError(f"capability authority input is not an object: {path}")
    return value


def _rows_by_id(document: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    rows = document.get("capabilities")
    if not isinstance(rows, list):
        raise CapabilityAuthorityError(f"{label} registry has no capabilities list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise CapabilityAuthorityError(f"{label} registry contains a malformed capability row")
        cid = row["id"]
        if cid in result:
            raise CapabilityAuthorityError(
                f"{label} registry contains duplicate capability id: {cid}"
            )
        result[cid] = row
    return result


def load_authoritative_capabilities(root: Path = ROOT) -> list[dict[str, Any]]:
    """Return a compatibility-shaped read view with each governed field from its owner.

    Canonical-definition fields come from Registry v1.  Mutable runtime,
    certification and repository-projection fields remain from the legacy projection
    until their own consumers are migrated.  Identity disagreement fails closed;
    reconciliation/ratchet machinery must resolve it before a consumer can guess.
    """
    policy_path = root / POLICY.relative_to(ROOT)
    canonical_path = root / CANONICAL.relative_to(ROOT)
    legacy_path = root / LEGACY.relative_to(ROOT)

    policy = _load_json(policy_path)
    if policy.get("schema") != POLICY_SCHEMA:
        raise CapabilityAuthorityError("field authority policy schema mismatch")
    reconciliation = policy.get("reconciliation")
    if (
        not isinstance(reconciliation, dict)
        or reconciliation.get("no_third_value_registry") is not True
    ):
        raise CapabilityAuthorityError("field authority policy must forbid a third value registry")
    field_authority = policy.get("field_authority")
    if not isinstance(field_authority, dict):
        raise CapabilityAuthorityError("field authority policy has no field_authority map")

    canonical = _rows_by_id(_load_json(canonical_path), "canonical")
    legacy = _rows_by_id(_load_json(legacy_path), "legacy")
    canonical_ids, legacy_ids = set(canonical), set(legacy)
    if canonical_ids != legacy_ids:
        only_canonical = sorted(canonical_ids - legacy_ids)
        only_legacy = sorted(legacy_ids - canonical_ids)
        raise CapabilityAuthorityError(
            f"capability identity sets disagree: canonical_only={only_canonical} legacy_only={only_legacy}"
        )

    canonical_fields = [
        field
        for field, spec in field_authority.items()
        if isinstance(spec, dict) and spec.get("authority") == "canonical_capability_definition"
    ]
    if not canonical_fields:
        raise CapabilityAuthorityError(
            "field authority policy grants no fields to canonical definition"
        )

    result: list[dict[str, Any]] = []
    for cid in sorted(canonical_ids):
        row = copy.deepcopy(legacy[cid])
        canonical_row = canonical[cid]
        for field in canonical_fields:
            if "." in field:
                # حقلٌ متداخل (مثل runtime.verification_receipts) لا يُدمَج بمفتاحٍ
                # مسطّح: يحتاج دامجاً صريحاً يوم تمنحه السياسة للتعريف القانونيّ —
                # والرفضُ هنا خيرٌ من كتابة مفتاحٍ حرفيّ باسمٍ منقوط لا يقرؤه أحد.
                raise CapabilityAuthorityError(
                    f"nested canonical field requires explicit merger: {field}"
                )
            if field not in canonical_row:
                raise CapabilityAuthorityError(
                    f"canonical capability {cid} lacks authoritative field: {field}"
                )
            row[field] = copy.deepcopy(canonical_row[field])
        result.append(row)
    return result
