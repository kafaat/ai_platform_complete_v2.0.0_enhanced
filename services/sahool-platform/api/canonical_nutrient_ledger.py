"""Canonical nutrient ledger for evidence-bound N/P/K accounting.

The ledger reconciles soil laboratory evidence, crop demand, canonical
phenology and verified as-applied operations.  It never invents laboratory
values or applied quantities and it does not dispatch fertilizer operations.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

_ALLOWED_NUTRIENTS = ("N", "P", "K")
# Per-nutrient validity of a soil laboratory value.  Mineral N (nitrate/ammonium) is
# mobile: leaching, denitrification and crop uptake change it within weeks, so a
# value older than ~6 weeks no longer describes the root zone.  Available P and
# exchangeable K are buffered by the soil and change over seasons, not weeks.
SOIL_SUPPLY_TTL_DAYS = {"N": 45, "P": 730, "K": 730}
_HARD_BLOCKS = frozenset(
    {
        "MISSING_SOIL_NUTRIENT_EVIDENCE",
        "STALE_SOIL_NUTRIENT_EVIDENCE",
        "MISSING_CROP_NUTRIENT_DEMAND",
        "UNKNOWN_PHENOLOGY_STAGE",
    }
)
_ALLOWED_STAGES = {"initial", "development", "mid", "late", "unknown"}
_HEX = set("0123456789abcdef")


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _finite_nonnegative(value: float | None, name: str) -> None:
    if value is not None and (not math.isfinite(value) or value < 0):
        raise ValueError(f"{name} must be finite and non-negative")


def _digest(value: str, name: str) -> None:
    if len(value) != 64 or any(ch not in _HEX for ch in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class SoilNutrientEvidence:
    sampled_at: datetime
    evidence_digest: str
    nitrogen_kg_ha: float | None = None
    phosphorus_kg_ha: float | None = None
    potassium_kg_ha: float | None = None
    organic_matter_pct: float | None = None


@dataclass(frozen=True)
class CropNutrientDemand:
    evidence_digest: str
    nitrogen_kg_ha: float | None = None
    phosphorus_kg_ha: float | None = None
    potassium_kg_ha: float | None = None
    target_yield_t_ha: float | None = None


@dataclass(frozen=True)
class NutrientApplication:
    operation_id: str
    applied_at: datetime
    evidence_digest: str
    verified: bool
    nitrogen_kg_ha: float = 0.0
    phosphorus_kg_ha: float = 0.0
    potassium_kg_ha: float = 0.0
    cost_amount: float | None = None
    currency: str | None = None


@dataclass(frozen=True)
class NutrientBalance:
    nutrient: str
    soil_supply_kg_ha: float | None
    crop_demand_kg_ha: float | None
    applied_kg_ha: float
    remaining_requirement_kg_ha: float | None
    surplus_kg_ha: float | None

    @property
    def actionable(self) -> bool:
        """A balance is actionable only when soil supply and demand are both known."""
        return (
            self.soil_supply_kg_ha is not None
            and self.crop_demand_kg_ha is not None
            and self.remaining_requirement_kg_ha is not None
        )


@dataclass(frozen=True)
class CanonicalNutrientLedger:
    tenant_id: str
    field_id: str
    season_id: str
    crop_id: str
    cultivar_id: str | None
    phenology_stage: str
    as_of: datetime
    status: str
    operational_recommendation_allowed: bool
    balances: tuple[NutrientBalance, ...]
    total_verified_cost: float | None
    currency: str | None
    verified_operation_ids: tuple[str, ...]
    limitations: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    ledger_digest: str


def _value(obj: object, nutrient: str) -> float | None:
    field = {"N": "nitrogen_kg_ha", "P": "phosphorus_kg_ha", "K": "potassium_kg_ha"}[nutrient]
    return getattr(obj, field)


def _derive_status(limitations: Iterable[str]) -> tuple[bool, str]:
    """The builder's rule: (operational_recommendation_allowed, status)."""
    limits = set(limitations)
    allowed = not (limits & _HARD_BLOCKS)
    if not allowed:
        return False, "blocked"
    return True, "managed_with_limitations" if limits else "managed"


def ledger_inconsistencies(ledger: CanonicalNutrientLedger) -> list[str]:
    """Re-derive what the builder would have concluded and list every disagreement.

    A ledger rebuilt from a stored payload (``CanonicalNutrientLedger(**payload)``)
    bypasses ``build_canonical_nutrient_ledger``; its ``operational_recommendation_allowed``
    and ``status`` are then claims, not derivations.  This re-applies the builder's
    own rules to the fields the ledger carries: the hard-block rule, the per-nutrient
    balance arithmetic (unknown or stale supply never closes a balance) and the
    canonical digest.  An empty list means the payload is internally consistent.
    """
    problems: list[str] = []
    limits = set(ledger.limitations)
    allowed, status = _derive_status(limits)
    if bool(ledger.operational_recommendation_allowed) is not allowed:
        problems.append("OPERATIONAL_ALLOWED_MISMATCH")
    if ledger.status != status:
        problems.append("STATUS_MISMATCH")
    if ledger.phenology_stage not in _ALLOWED_STAGES:
        problems.append("UNKNOWN_PHENOLOGY_STAGE_VALUE")
    if tuple(b.nutrient for b in ledger.balances) != _ALLOWED_NUTRIENTS:
        problems.append("BALANCE_SET_MISMATCH")
        return problems
    for b in ledger.balances:
        n = b.nutrient
        supply, required, applied = b.soil_supply_kg_ha, b.crop_demand_kg_ha, b.applied_kg_ha
        values = (supply, required, applied, b.remaining_requirement_kg_ha, b.surplus_kg_ha)
        if (
            any(
                v is not None
                and (
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not math.isfinite(v)
                    or v < 0
                )
                for v in values
            )
            or applied is None
        ):
            problems.append(f"{n}_BALANCE_VALUE_INVALID")
            continue
        if (supply is None) is not (f"MISSING_{n}_SOIL_SUPPLY" in limits):
            problems.append(f"{n}_SOIL_SUPPLY_LIMITATION_MISMATCH")
        if (required is None) is not (f"MISSING_{n}_DEMAND" in limits):
            problems.append(f"{n}_DEMAND_LIMITATION_MISMATCH")
        closable = (
            supply is not None and required is not None and f"STALE_{n}_SOIL_SUPPLY" not in limits
        )
        if not closable:
            if b.remaining_requirement_kg_ha is not None or b.surplus_kg_ha is not None:
                problems.append(f"{n}_BALANCE_CLOSED_WITHOUT_SUPPLY")
            continue
        available = float(supply) + applied
        expected_remaining = round(max(0.0, required - available), 6)
        expected_surplus = round(max(0.0, available - required), 6)
        if (
            b.remaining_requirement_kg_ha is None
            or b.surplus_kg_ha is None
            or not math.isclose(b.remaining_requirement_kg_ha, expected_remaining, abs_tol=1e-6)
            or not math.isclose(b.surplus_kg_ha, expected_surplus, abs_tol=1e-6)
        ):
            problems.append(f"{n}_BALANCE_ARITHMETIC_MISMATCH")
    try:
        as_of = _aware(ledger.as_of, "as_of")
    except (AttributeError, ValueError):
        problems.append("AS_OF_INVALID")
        return problems
    payload = {
        "tenant_id": ledger.tenant_id,
        "field_id": ledger.field_id,
        "season_id": ledger.season_id,
        "crop_id": ledger.crop_id,
        "cultivar_id": ledger.cultivar_id,
        "phenology_stage": ledger.phenology_stage,
        "as_of": as_of.isoformat(),
        "status": ledger.status,
        "operational_recommendation_allowed": ledger.operational_recommendation_allowed,
        "balances": [asdict(item) for item in ledger.balances],
        "total_verified_cost": ledger.total_verified_cost,
        "currency": ledger.currency,
        "verified_operation_ids": sorted(ledger.verified_operation_ids),
        "limitations": sorted(limits),
        "evidence_digests": sorted(set(ledger.evidence_digests)),
    }
    if _hash(payload) != ledger.ledger_digest:
        problems.append("LEDGER_DIGEST_MISMATCH")
    return problems


def build_canonical_nutrient_ledger(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    crop_id: str,
    cultivar_id: str | None,
    phenology_stage: str,
    as_of: datetime,
    soil: SoilNutrientEvidence | None,
    demand: CropNutrientDemand | None,
    applications: Iterable[NutrientApplication],
    max_soil_age_days: int = 730,
    season_start: datetime | None = None,
) -> CanonicalNutrientLedger:
    """Build a deterministic N/P/K ledger from immutable evidence.

    Operational recommendations are permitted only when current soil evidence,
    crop demand and a known canonical phenology stage are available. Verified
    applications are included; unverified operations are ignored and reported.

    Each soil value is valid for ``SOIL_SUPPLY_TTL_DAYS[nutrient]`` (capped by
    ``max_soil_age_days``); a stale value keeps the other nutrients usable but makes
    its own balance non-actionable (``STALE_<N>_SOIL_SUPPLY``).  Applications dated
    before ``soil.sampled_at`` are already reflected in the laboratory value and are
    excluded (``APPLICATION_BEFORE_SOIL_SAMPLE``), as are applications before the
    optional ``season_start`` (``APPLICATION_BEFORE_SEASON_START``).
    """
    as_of = _aware(as_of, "as_of")
    if not all((tenant_id, field_id, season_id, crop_id)):
        raise ValueError("tenant_id, field_id, season_id and crop_id are required")
    if phenology_stage not in _ALLOWED_STAGES:
        raise ValueError("unknown phenology_stage")
    if max_soil_age_days < 1:
        raise ValueError("max_soil_age_days must be positive")

    if season_start is not None:
        season_start = _aware(season_start, "season_start")
        if season_start > as_of:
            raise ValueError("season_start cannot be after as_of")

    limitations: list[str] = []
    digests: list[str] = []
    stale_supply: set[str] = set()
    sampled_at: datetime | None = None

    if soil is None:
        limitations.append("MISSING_SOIL_NUTRIENT_EVIDENCE")
    else:
        sampled_at = _aware(soil.sampled_at, "soil.sampled_at")
        _digest(soil.evidence_digest, "soil.evidence_digest")
        digests.append(soil.evidence_digest)
        for nutrient in _ALLOWED_NUTRIENTS:
            _finite_nonnegative(_value(soil, nutrient), f"soil.{nutrient}")
        _finite_nonnegative(soil.organic_matter_pct, "soil.organic_matter_pct")
        age = as_of - sampled_at
        if not timedelta(0) <= age <= timedelta(days=max_soil_age_days):
            limitations.append("STALE_SOIL_NUTRIENT_EVIDENCE")
        for nutrient in _ALLOWED_NUTRIENTS:
            ttl = min(SOIL_SUPPLY_TTL_DAYS[nutrient], max_soil_age_days)
            if _value(soil, nutrient) is not None and not timedelta(0) <= age <= timedelta(
                days=ttl
            ):
                stale_supply.add(nutrient)
                limitations.append(f"STALE_{nutrient}_SOIL_SUPPLY")

    if demand is None:
        limitations.append("MISSING_CROP_NUTRIENT_DEMAND")
    else:
        _digest(demand.evidence_digest, "demand.evidence_digest")
        digests.append(demand.evidence_digest)
        for nutrient in _ALLOWED_NUTRIENTS:
            _finite_nonnegative(_value(demand, nutrient), f"demand.{nutrient}")
        _finite_nonnegative(demand.target_yield_t_ha, "demand.target_yield_t_ha")

    if phenology_stage == "unknown":
        limitations.append("UNKNOWN_PHENOLOGY_STAGE")

    applied = {n: 0.0 for n in _ALLOWED_NUTRIENTS}
    verified_ids: list[str] = []
    total_cost = 0.0
    saw_cost = False
    currency: str | None = None

    ordered = sorted(
        applications,
        key=lambda item: (_aware(item.applied_at, "application.applied_at"), item.operation_id),
    )
    seen_ids: set[str] = set()
    for item in ordered:
        if not item.operation_id:
            raise ValueError("application.operation_id is required")
        if item.operation_id in seen_ids:
            raise ValueError(f"duplicate application operation_id: {item.operation_id}")
        seen_ids.add(item.operation_id)
        applied_at = _aware(item.applied_at, "application.applied_at")
        if applied_at > as_of:
            raise ValueError("application.applied_at cannot be in the future")
        _digest(item.evidence_digest, "application.evidence_digest")
        for nutrient in _ALLOWED_NUTRIENTS:
            _finite_nonnegative(_value(item, nutrient), f"application.{nutrient}")
        _finite_nonnegative(item.cost_amount, "application.cost_amount")
        if season_start is not None and applied_at < season_start:
            limitations.append("APPLICATION_BEFORE_SEASON_START")
            continue
        if sampled_at is not None and applied_at < sampled_at:
            # The laboratory value already contains this application; crediting it
            # again would count the same nutrient twice.
            limitations.append("APPLICATION_BEFORE_SOIL_SAMPLE")
            continue
        if not item.verified:
            limitations.append(f"UNVERIFIED_APPLICATION_IGNORED:{item.operation_id}")
            continue
        if item.cost_amount is not None:
            if not item.currency:
                raise ValueError("verified application cost requires currency")
            if currency is None:
                currency = item.currency
            elif currency != item.currency:
                raise ValueError("mixed currencies are not allowed in one ledger")
            total_cost += item.cost_amount
            saw_cost = True
        for nutrient in _ALLOWED_NUTRIENTS:
            applied[nutrient] += float(_value(item, nutrient) or 0.0)
        verified_ids.append(item.operation_id)
        digests.append(item.evidence_digest)

    balances: list[NutrientBalance] = []
    for nutrient in _ALLOWED_NUTRIENTS:
        supply = _value(soil, nutrient) if soil else None
        required = _value(demand, nutrient) if demand else None
        amount = round(applied[nutrient], 6)
        remaining = surplus = None
        # Unknown soil supply is not zero supply: without a laboratory value the
        # balance cannot be closed, so the nutrient stays non-actionable.  A stale
        # value is reported but not used to close the balance either.
        if required is not None and supply is not None and nutrient not in stale_supply:
            available = float(supply) + amount
            remaining = round(max(0.0, required - available), 6)
            surplus = round(max(0.0, available - required), 6)
        balances.append(
            NutrientBalance(
                nutrient=nutrient,
                soil_supply_kg_ha=supply,
                crop_demand_kg_ha=required,
                applied_kg_ha=amount,
                remaining_requirement_kg_ha=remaining,
                surplus_kg_ha=surplus,
            )
        )
        if required is None:
            limitations.append(f"MISSING_{nutrient}_DEMAND")
        if supply is None:
            limitations.append(f"MISSING_{nutrient}_SOIL_SUPPLY")

    operational_allowed, status = _derive_status(limitations)

    payload = {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "season_id": season_id,
        "crop_id": crop_id,
        "cultivar_id": cultivar_id,
        "phenology_stage": phenology_stage,
        "as_of": as_of.isoformat(),
        "status": status,
        "operational_recommendation_allowed": operational_allowed,
        "balances": [asdict(item) for item in balances],
        "total_verified_cost": round(total_cost, 6) if saw_cost else None,
        "currency": currency,
        "verified_operation_ids": sorted(verified_ids),
        "limitations": sorted(set(limitations)),
        "evidence_digests": sorted(set(digests)),
    }
    digest = _hash(payload)
    return CanonicalNutrientLedger(
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        crop_id=crop_id,
        cultivar_id=cultivar_id,
        phenology_stage=phenology_stage,
        as_of=as_of,
        status=status,
        operational_recommendation_allowed=operational_allowed,
        balances=tuple(balances),
        total_verified_cost=payload["total_verified_cost"],
        currency=currency,
        verified_operation_ids=tuple(sorted(verified_ids)),
        limitations=tuple(payload["limitations"]),
        evidence_digests=tuple(payload["evidence_digests"]),
        ledger_digest=digest,
    )
