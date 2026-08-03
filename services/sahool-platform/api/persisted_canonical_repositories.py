"""Tenant-scoped repositories for persisted canonical agricultural truth.

All functions require a connection already scoped by ``tenant_connection`` or an
explicit worker transaction that set ``app.current_tenant``. Callers provide
identifiers only; canonical objects are reconstructed from persisted rows.
"""

from __future__ import annotations

import json
from typing import Any

from api.canonical_nutrient_ledger import CanonicalNutrientLedger, NutrientBalance
from api.canonical_phenology_state import CanonicalPhenologyState
from api.canonical_salinity_state import CanonicalSalinityState


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


async def load_active_season_id(conn: Any, *, field_id: str) -> str | None:
    row = await conn.fetchrow(
        "SELECT season_id FROM seasons WHERE field_id=$1 AND status='active' "
        "ORDER BY sowing_date DESC NULLS LAST LIMIT 1",
        field_id,
    )
    return str(row["season_id"]) if row else None


async def load_phenology_state(
    conn: Any, *, field_id: str, season_id: str
) -> CanonicalPhenologyState | None:
    row = await conn.fetchrow(
        "SELECT * FROM canonical_phenology_states WHERE field_id=$1 AND season_id=$2 "
        "ORDER BY as_of DESC, created_at DESC LIMIT 1",
        field_id,
        season_id,
    )
    if not row:
        return None
    return CanonicalPhenologyState(
        tenant_id=str(row["tenant_id"]),
        field_id=row["field_id"],
        season_id=row["season_id"],
        crop_id=row["crop_id"],
        cultivar_id=row["cultivar_id"],
        as_of=row["as_of"],
        sowing_date=row["sowing_date"],
        days_since_sowing=row["days_since_sowing"],
        observed_stage=row["observed_stage"],
        predicted_stage=row["predicted_stage"],
        canonical_stage=row["canonical_stage"],
        status=row["status"],
        confidence=row["confidence"],
        accumulated_gdd=row["accumulated_gdd"],
        gdd_fraction=row["gdd_fraction"],
        stage_divergence=row["stage_divergence"],
        observation_ids=tuple(_json(row["observation_ids"], [])),
        evidence_digests=tuple(_json(row["evidence_digests"], [])),
        limitations=tuple(_json(row["limitations"], [])),
        state_digest=row["state_digest"],
    )


async def load_salinity_state(
    conn: Any, *, field_id: str, season_id: str
) -> CanonicalSalinityState | None:
    row = await conn.fetchrow(
        "SELECT * FROM canonical_salinity_states WHERE field_id=$1 AND season_id=$2 "
        "ORDER BY as_of DESC, created_at DESC LIMIT 1",
        field_id,
        season_id,
    )
    if not row:
        return None
    return CanonicalSalinityState(
        tenant_id=str(row["tenant_id"]),
        field_id=row["field_id"],
        season_id=row["season_id"],
        crop_id=row["crop_id"],
        cultivar_id=row["cultivar_id"],
        phenology_stage=row["phenology_stage"],
        as_of=row["as_of"],
        status=row["status"],
        soil_class=row["soil_class"],
        water_risk=row["water_risk"],
        sodium_hazard_class=row["sodium_hazard_class"],
        rsc_hazard_class=row["rsc_hazard_class"],
        effective_crop_threshold_ece_dsm=row["effective_crop_threshold_ece_dsm"],
        estimated_relative_yield=row["estimated_relative_yield"],
        leaching_fraction=row["leaching_fraction"],
        leaching_feasible=row["leaching_feasible"],
        drainage_class=row["drainage_class"],
        operational_recommendation_allowed=row["operational_recommendation_allowed"],
        limitations=tuple(_json(row["limitations"], [])),
        evidence_digests=tuple(_json(row["evidence_digests"], [])),
        state_digest=row["state_digest"],
    )


async def load_nutrient_ledger(
    conn: Any, *, field_id: str, season_id: str
) -> CanonicalNutrientLedger | None:
    row = await conn.fetchrow(
        "SELECT * FROM canonical_nutrient_ledgers WHERE field_id=$1 AND season_id=$2 "
        "ORDER BY as_of DESC, created_at DESC LIMIT 1",
        field_id,
        season_id,
    )
    if not row:
        return None
    balances = tuple(NutrientBalance(**item) for item in _json(row["balances"], []))
    return CanonicalNutrientLedger(
        tenant_id=str(row["tenant_id"]),
        field_id=row["field_id"],
        season_id=row["season_id"],
        crop_id=row["crop_id"],
        cultivar_id=row["cultivar_id"],
        phenology_stage=row["phenology_stage"],
        as_of=row["as_of"],
        status=row["status"],
        operational_recommendation_allowed=row["operational_recommendation_allowed"],
        balances=balances,
        total_verified_cost=float(row["total_verified_cost"])
        if row["total_verified_cost"] is not None
        else None,
        currency=row["currency"],
        verified_operation_ids=tuple(_json(row["verified_operation_ids"], [])),
        limitations=tuple(_json(row["limitations"], [])),
        evidence_digests=tuple(_json(row["evidence_digests"], [])),
        ledger_digest=row["ledger_digest"],
    )


async def load_agronomic_context(conn: Any, *, field_id: str) -> dict[str, Any]:
    """Load persisted canonical context for the active season under RLS."""
    season_id = await load_active_season_id(conn, field_id=field_id)
    if not season_id:
        return {"season_id": None, "phenology": None, "salinity": None, "nutrients": None}
    phenology = await load_phenology_state(conn, field_id=field_id, season_id=season_id)
    salinity = await load_salinity_state(conn, field_id=field_id, season_id=season_id)
    nutrients = await load_nutrient_ledger(conn, field_id=field_id, season_id=season_id)
    return {
        "season_id": season_id,
        "phenology": phenology,
        "salinity": salinity,
        "nutrients": nutrients,
    }
