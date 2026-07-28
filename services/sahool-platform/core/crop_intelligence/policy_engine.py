from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

_SCHEMA = "crop_policy_assessment.v1"
_POLICY_ENGINE_VERSION = "crop-policy/1.0.0"
_ALLOWED_PACK_TYPES = {"crop", "water", "weather", "regional", "cultivar", "business"}
_ALLOWED_TRIGGERS = {
    "water_needs_irrigation",
    "spectral_water_stress_confirmed",
    "weather_heat_stress",
    "weather_frost_risk",
    "crop_water_urgency_high",
}
_REQUIRED_PACK_TYPES = tuple(sorted(_ALLOWED_PACK_TYPES))


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    trigger: str
    stress_code: str | None = None
    urgency_factor: str | None = None


@dataclass(frozen=True)
class PolicyPack:
    pack_type: str
    policy_id: str
    version: str
    rules: tuple[PolicyRule, ...]
    source_ids: tuple[str, ...] = ()


def default_policy_packs() -> tuple[PolicyPack, ...]:
    """Return the versioned baseline policy set; scientific products remain external facts."""
    return (
        PolicyPack("crop", "sahool.crop.baseline", "1.0.0", ()),
        PolicyPack(
            "water",
            "sahool.water.baseline",
            "1.0.0",
            (
                PolicyRule("water-deficit", "water_needs_irrigation", stress_code="water_deficit"),
                PolicyRule(
                    "spectral-water-stress",
                    "spectral_water_stress_confirmed",
                    stress_code="spectral_water_stress",
                ),
                PolicyRule(
                    "water-urgency-high",
                    "crop_water_urgency_high",
                    urgency_factor="water_urgency_high",
                ),
            ),
        ),
        PolicyPack(
            "weather",
            "sahool.weather.baseline",
            "1.0.0",
            (
                PolicyRule(
                    "heat-stress",
                    "weather_heat_stress",
                    stress_code="heat_stress",
                    urgency_factor="heat_stress",
                ),
                PolicyRule(
                    "frost-risk",
                    "weather_frost_risk",
                    stress_code="frost_risk",
                    urgency_factor="frost_risk",
                ),
            ),
        ),
        PolicyPack("regional", "sahool.regional.default", "1.0.0", ()),
        PolicyPack("cultivar", "sahool.cultivar.default", "1.0.0", ()),
        PolicyPack("business", "sahool.business.default", "1.0.0", ()),
    )


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_packs(packs: Iterable[PolicyPack]) -> tuple[PolicyPack, ...]:
    materialized = tuple(packs)
    types = [p.pack_type for p in materialized]
    invalid_types = sorted(set(types) - _ALLOWED_PACK_TYPES)
    if invalid_types:
        raise ValueError(f"unsupported policy pack types: {invalid_types}")
    missing = sorted(set(_REQUIRED_PACK_TYPES) - set(types))
    if missing:
        raise ValueError(f"missing required policy pack types: {missing}")
    duplicate_types = sorted({t for t in types if types.count(t) > 1})
    if duplicate_types:
        raise ValueError(f"duplicate policy pack types: {duplicate_types}")

    rule_ids: list[str] = []
    for pack in materialized:
        if not pack.policy_id or not pack.version:
            raise ValueError("policy_id and version are required")
        for rule in pack.rules:
            if rule.trigger not in _ALLOWED_TRIGGERS:
                raise ValueError(f"unsupported policy trigger: {rule.trigger}")
            if not rule.stress_code and not rule.urgency_factor:
                raise ValueError(f"policy rule has no effect: {rule.rule_id}")
            rule_ids.append(rule.rule_id)
    duplicates = sorted({rule_id for rule_id in rule_ids if rule_ids.count(rule_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate policy rule ids: {duplicates}")
    return materialized


def evaluate_crop_policy(
    *,
    facts: dict[str, bool],
    packs: Iterable[PolicyPack] | None = None,
) -> dict[str, Any]:
    selected = _validate_packs(packs or default_policy_packs())
    stress_flags: list[dict[str, str]] = []
    urgent_factors: list[str] = []
    matched_rules: list[str] = []
    evidence_ids: list[str] = []

    for pack in selected:
        evidence_ids.extend(pack.source_ids)
        evidence_ids.append(f"policy:{pack.policy_id}@{pack.version}")
        for rule in pack.rules:
            if facts.get(rule.trigger) is not True:
                continue
            matched_rules.append(rule.rule_id)
            if rule.stress_code:
                stress_flags.append(
                    {"code": rule.stress_code, "source": f"policy:{pack.policy_id}"}
                )
            if rule.urgency_factor:
                urgent_factors.append(rule.urgency_factor)

    manifest = [
        {
            "pack_type": pack.pack_type,
            "policy_id": pack.policy_id,
            "version": pack.version,
            "rules": [rule.rule_id for rule in pack.rules],
        }
        for pack in selected
    ]
    return {
        "schema": _SCHEMA,
        "engine_version": _POLICY_ENGINE_VERSION,
        "policy_manifest": manifest,
        "policy_digest": _canonical_digest(manifest),
        "matched_rule_ids": list(dict.fromkeys(matched_rules)),
        "stress_flags": list({(f["code"], f["source"]): f for f in stress_flags}.values()),
        "urgency": "high" if urgent_factors else "normal",
        "urgent_factors": list(dict.fromkeys(urgent_factors)),
        "evidence_ids": list(dict.fromkeys(evidence_ids)),
        "decision_boundary": {"is_decision": False, "consumer": "decision-service"},
    }
