"""Tenant-scoped repositories for persisted canonical agricultural truth.

All functions require a connection already scoped by ``tenant_connection`` or an
explicit worker transaction that set ``app.current_tenant``. Callers provide
identifiers only; canonical objects are reconstructed from persisted rows.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any
from uuid import UUID

from api.canonical_nutrient_ledger import CanonicalNutrientLedger, NutrientBalance
from api.canonical_phenology_state import CanonicalPhenologyState, PhenologyObservation
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


def _inserted(status: str) -> bool:
    """Return whether an asyncpg INSERT command inserted a new row."""
    parts = str(status).split()
    return bool(parts and parts[-1] == "1")


async def persist_phenology_state(conn: Any, state: CanonicalPhenologyState) -> bool:
    """Persist one immutable phenology projection idempotently under tenant RLS."""
    status = await conn.execute(
        """
        INSERT INTO canonical_phenology_states (
            tenant_id, state_digest, field_id, season_id, crop_id, cultivar_id,
            as_of, sowing_date, days_since_sowing, observed_stage, predicted_stage,
            canonical_stage, status, confidence, accumulated_gdd, gdd_fraction,
            stage_divergence, observation_ids, evidence_digests, limitations
        ) VALUES (
            $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,
            $18::jsonb,$19::jsonb,$20::jsonb
        ) ON CONFLICT (tenant_id, state_digest) DO NOTHING
        """,
        state.tenant_id,
        state.state_digest,
        state.field_id,
        state.season_id,
        state.crop_id,
        state.cultivar_id,
        state.as_of,
        state.sowing_date,
        state.days_since_sowing,
        state.observed_stage,
        state.predicted_stage,
        state.canonical_stage,
        state.status,
        state.confidence,
        state.accumulated_gdd,
        state.gdd_fraction,
        state.stage_divergence,
        json.dumps(list(state.observation_ids)),
        json.dumps(list(state.evidence_digests)),
        json.dumps(list(state.limitations)),
    )
    return _inserted(status)


async def persist_salinity_state(conn: Any, state: CanonicalSalinityState) -> bool:
    """Persist one immutable salinity projection idempotently under tenant RLS."""
    status = await conn.execute(
        """
        INSERT INTO canonical_salinity_states (
            tenant_id, state_digest, field_id, season_id, crop_id, cultivar_id,
            phenology_stage, as_of, status, soil_class, water_risk,
            sodium_hazard_class, rsc_hazard_class, effective_crop_threshold_ece_dsm,
            estimated_relative_yield, leaching_fraction, leaching_feasible,
            drainage_class, operational_recommendation_allowed, limitations, evidence_digests
        ) VALUES (
            $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,
            $20::jsonb,$21::jsonb
        ) ON CONFLICT (tenant_id, state_digest) DO NOTHING
        """,
        state.tenant_id,
        state.state_digest,
        state.field_id,
        state.season_id,
        state.crop_id,
        state.cultivar_id,
        state.phenology_stage,
        state.as_of,
        state.status,
        state.soil_class,
        state.water_risk,
        state.sodium_hazard_class,
        state.rsc_hazard_class,
        state.effective_crop_threshold_ece_dsm,
        state.estimated_relative_yield,
        state.leaching_fraction,
        state.leaching_feasible,
        state.drainage_class,
        state.operational_recommendation_allowed,
        json.dumps(list(state.limitations)),
        json.dumps(list(state.evidence_digests)),
    )
    return _inserted(status)


async def persist_nutrient_ledger(conn: Any, ledger: CanonicalNutrientLedger) -> bool:
    """Persist one immutable nutrient-ledger projection idempotently under tenant RLS."""
    status = await conn.execute(
        """
        INSERT INTO canonical_nutrient_ledgers (
            tenant_id, field_id, season_id, crop_id, cultivar_id, phenology_stage, as_of,
            status, operational_recommendation_allowed, balances, total_verified_cost,
            currency, verified_operation_ids, limitations, evidence_digests, ledger_digest
        ) VALUES (
            $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11,$12,$13::jsonb,$14::jsonb,
            $15::jsonb,$16
        ) ON CONFLICT (tenant_id, field_id, season_id, ledger_digest) DO NOTHING
        """,
        ledger.tenant_id,
        ledger.field_id,
        ledger.season_id,
        ledger.crop_id,
        ledger.cultivar_id,
        ledger.phenology_stage,
        ledger.as_of,
        ledger.status,
        ledger.operational_recommendation_allowed,
        json.dumps([asdict(item) for item in ledger.balances]),
        ledger.total_verified_cost,
        ledger.currency,
        json.dumps(list(ledger.verified_operation_ids)),
        json.dumps(list(ledger.limitations)),
        json.dumps(list(ledger.evidence_digests)),
        ledger.ledger_digest,
    )
    return _inserted(status)


_EMIT_PROJECTION_SQL = """
SELECT emit_event(
    $1::text, 'field'::text, $2::text, $3::uuid, $4::jsonb,
    'sahool-platform'::text, NULL::text, $5::uuid, $6::timestamptz
)
"""


async def _emit_projection_event(
    conn: Any,
    *,
    event_type: str,
    tenant_id: str,
    field_id: str,
    season_id: str,
    digest: str,
    as_of: Any,
) -> str | None:
    payload = {
        "field_id": field_id,
        "season_id": season_id,
        "state_digest": digest,
        "projection": event_type.removesuffix(".projected"),
    }
    event_id = await conn.fetchval(
        _EMIT_PROJECTION_SQL,
        event_type,
        field_id,
        UUID(str(tenant_id)),
        json.dumps(payload, sort_keys=True),
        None,
        as_of,
    )
    return str(event_id) if event_id is not None else None


def _require_same_scope(
    *, tenant_id: str, field_id: str, season_id: str, row: dict[str, Any]
) -> None:
    for key, expected in (
        ("tenant_id", tenant_id),
        ("field_id", field_id),
        ("season_id", season_id),
    ):
        if str(row.get(key)) != str(expected):
            raise ValueError(f"evidence {key} does not match canonical projection scope")


async def persist_phenology_projection(
    conn: Any,
    state: CanonicalPhenologyState,
    observations: list[PhenologyObservation],
) -> tuple[bool, str | None]:
    """Persist raw observations, canonical state, and outbox event atomically.

    The caller owns the transaction. Replays are idempotent at the evidence,
    state, and event layers.
    """
    expected = set(state.observation_ids)
    supplied = {item.observation_id for item in observations}
    if expected != supplied:
        raise ValueError("phenology observations do not match state observation_ids")
    for item in observations:
        obs = item.normalized()
        if obs.evidence_digest not in set(state.evidence_digests):
            raise ValueError("phenology observation digest is not bound to canonical state")
        await conn.execute(
            """
            INSERT INTO phenology_observations (
                tenant_id, observation_id, field_id, season_id, crop_id, cultivar_id,
                source, stage, observed_at, confidence, evidence_digest
            ) VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            ON CONFLICT (tenant_id, observation_id) DO NOTHING
            """,
            state.tenant_id,
            obs.observation_id,
            state.field_id,
            state.season_id,
            state.crop_id,
            state.cultivar_id,
            obs.source,
            obs.stage,
            obs.observed_at,
            obs.confidence,
            obs.evidence_digest,
        )
    inserted = await persist_phenology_state(conn, state)
    event_id = None
    if inserted:
        event_id = await _emit_projection_event(
            conn,
            event_type="agronomy.phenology.projected",
            tenant_id=state.tenant_id,
            field_id=state.field_id,
            season_id=state.season_id,
            digest=state.state_digest,
            as_of=state.as_of,
        )
    return inserted, event_id


async def persist_salinity_projection(
    conn: Any,
    state: CanonicalSalinityState,
    evidence: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    """Persist salinity evidence, state, and one idempotent outbox intent."""
    state_digests = set(state.evidence_digests)
    for row in evidence:
        _require_same_scope(
            tenant_id=state.tenant_id,
            field_id=state.field_id,
            season_id=state.season_id,
            row=row,
        )
        digest = str(row.get("evidence_digest", ""))
        if digest not in state_digests:
            raise ValueError("salinity evidence digest is not bound to canonical state")
        await conn.execute(
            """
            INSERT INTO salinity_evidence_observations (
                tenant_id, evidence_id, field_id, season_id, evidence_type,
                observed_at, evidence_digest, payload
            ) VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8::jsonb)
            ON CONFLICT (tenant_id, evidence_id) DO NOTHING
            """,
            state.tenant_id,
            str(row["evidence_id"]),
            state.field_id,
            state.season_id,
            str(row["evidence_type"]),
            row["observed_at"],
            digest,
            json.dumps(row.get("payload", {}), sort_keys=True),
        )
    inserted = await persist_salinity_state(conn, state)
    event_id = None
    if inserted:
        event_id = await _emit_projection_event(
            conn,
            event_type="agronomy.salinity.projected",
            tenant_id=state.tenant_id,
            field_id=state.field_id,
            season_id=state.season_id,
            digest=state.state_digest,
            as_of=state.as_of,
        )
    return inserted, event_id


async def persist_nutrient_projection(
    conn: Any,
    ledger: CanonicalNutrientLedger,
    evidence: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    """Persist nutrient evidence, canonical ledger, and one outbox intent."""
    ledger_digests = set(ledger.evidence_digests)
    for row in evidence:
        _require_same_scope(
            tenant_id=ledger.tenant_id,
            field_id=ledger.field_id,
            season_id=ledger.season_id,
            row=row,
        )
        digest = str(row.get("evidence_digest", ""))
        if digest not in ledger_digests:
            raise ValueError("nutrient evidence digest is not bound to canonical ledger")
        await conn.execute(
            """
            INSERT INTO nutrient_evidence_observations (
                tenant_id, field_id, season_id, evidence_type, observed_at,
                evidence_digest, payload
            ) VALUES ($1::uuid,$2,$3,$4,$5,$6,$7::jsonb)
            ON CONFLICT (tenant_id, evidence_digest) DO NOTHING
            """,
            ledger.tenant_id,
            ledger.field_id,
            ledger.season_id,
            str(row["evidence_type"]),
            row["observed_at"],
            digest,
            json.dumps(row.get("payload", {}), sort_keys=True),
        )
    inserted = await persist_nutrient_ledger(conn, ledger)
    event_id = None
    if inserted:
        event_id = await _emit_projection_event(
            conn,
            event_type="agronomy.nutrients.projected",
            tenant_id=ledger.tenant_id,
            field_id=ledger.field_id,
            season_id=ledger.season_id,
            digest=ledger.ledger_digest,
            as_of=ledger.as_of,
        )
    return inserted, event_id
