"""Durable canonical soil evidence and snapshot persistence."""

from __future__ import annotations

import json
from typing import Any

from shared.contracts.soil import SoilObservation, SoilProfileSnapshot


async def _tenant_tx(conn, tenant_id: str):
    tx = conn.transaction()
    await tx.start()
    await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant_id)
    return tx


async def persist_observation(pool, observation: SoilObservation) -> bool:
    async with pool.acquire() as conn:
        tx = await _tenant_tx(conn, observation.tenant_id)
        try:
            result = await conn.execute(
                """
                INSERT INTO soil_observations (
                    observation_id, contract_version, tenant_id, field_id, zone_id,
                    property, value_json, unit, depth_from_cm, depth_to_cm,
                    observed_at, received_at, source_type, source_id, procedure_id,
                    calibration_id, quality_status, quality_flags, confidence,
                    idempotency_key, provenance
                ) VALUES (
                    $1,$2,$3::uuid,$4,$5,$6,$7::jsonb,$8,$9,$10,$11,$12,$13,$14,$15,
                    $16,$17,$18::jsonb,$19,$20,$21::jsonb
                )
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                """,
                observation.observation_id,
                observation.contract_version,
                observation.tenant_id,
                observation.field_id,
                observation.zone_id,
                observation.property,
                json.dumps(observation.value),
                observation.unit,
                observation.depth_from_cm,
                observation.depth_to_cm,
                observation.observed_at,
                observation.received_at,
                observation.source_type.value,
                observation.source_id,
                observation.procedure_id,
                observation.calibration_id,
                observation.quality_status.value,
                json.dumps(observation.quality_flags),
                observation.confidence,
                observation.idempotency_key,
                json.dumps(observation.provenance),
            )
            await tx.commit()
            return result.endswith("1")
        except Exception:
            await tx.rollback()
            raise


async def list_observations(
    pool,
    *,
    tenant_id: str,
    field_id: str,
    property_name: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        tx = await _tenant_tx(conn, tenant_id)
        try:
            rows = await conn.fetch(
                """
                SELECT observation_id, contract_version, tenant_id::text, field_id, zone_id,
                       property, value_json, unit, depth_from_cm, depth_to_cm,
                       observed_at, received_at, source_type, source_id, procedure_id,
                       calibration_id, quality_status, quality_flags, confidence,
                       idempotency_key, provenance
                FROM soil_observations
                WHERE tenant_id = $1::uuid AND field_id = $2
                  AND ($3::text IS NULL OR property = $3)
                ORDER BY observed_at DESC
                LIMIT $4
                """,
                tenant_id,
                field_id,
                property_name,
                limit,
            )
            await tx.commit()
            return [dict(row) for row in rows]
        except Exception:
            await tx.rollback()
            raise


async def persist_snapshot(pool, snapshot: SoilProfileSnapshot) -> bool:
    payload = snapshot.model_dump(mode="json")
    async with pool.acquire() as conn:
        tx = await _tenant_tx(conn, str(snapshot.tenant_id))
        try:
            result = await conn.execute(
                """
                INSERT INTO soil_profile_snapshots (
                    profile_id, profile_hash, contract_version, tenant_id, field_id, zone_id,
                    effective_at, data_available_at, status, evidence_level,
                    completeness_score, quality_passed, executable,
                    selection_policy_version, snapshot
                ) VALUES ($1,$2,$3,$4::uuid,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)
                ON CONFLICT (profile_hash) DO NOTHING
                """,
                snapshot.profile_id,
                snapshot.profile_hash,
                snapshot.contract_version,
                snapshot.tenant_id,
                snapshot.field_id,
                snapshot.zone_id,
                snapshot.effective_at,
                snapshot.data_available_at,
                snapshot.status.value,
                snapshot.evidence_level.value,
                snapshot.completeness_score,
                snapshot.quality_gate.passed,
                snapshot.quality_gate.executable,
                snapshot.selection_policy_version,
                json.dumps(payload),
            )
            await tx.commit()
            return result.endswith("1")
        except Exception:
            await tx.rollback()
            raise


async def get_current_snapshot(pool, *, tenant_id: str, field_id: str) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        tx = await _tenant_tx(conn, tenant_id)
        try:
            row = await conn.fetchrow(
                """
                SELECT snapshot
                FROM soil_profile_snapshots
                WHERE tenant_id=$1::uuid AND field_id=$2
                ORDER BY effective_at DESC, created_at DESC
                LIMIT 1
                """,
                tenant_id,
                field_id,
            )
            await tx.commit()
            return dict(row["snapshot"]) if row else None
        except Exception:
            await tx.rollback()
            raise


async def get_snapshot_history(
    pool, *, tenant_id: str, field_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        tx = await _tenant_tx(conn, tenant_id)
        try:
            rows = await conn.fetch(
                """
                SELECT snapshot
                FROM soil_profile_snapshots
                WHERE tenant_id=$1::uuid AND field_id=$2
                ORDER BY effective_at DESC, created_at DESC
                LIMIT $3
                """,
                tenant_id,
                field_id,
                limit,
            )
            await tx.commit()
            return [dict(row["snapshot"]) for row in rows]
        except Exception:
            await tx.rollback()
            raise


async def rebuild_snapshot_locked(pool, *, tenant_id: str, field_id: str) -> SoilProfileSnapshot:
    """Build and persist one immutable projection under a per-tenant/field advisory lock.

    The lock prevents duplicate competing projections across workers. The resulting
    profile hash remains the idempotency identity, so retries are logically exactly-once.
    """
    import profile_composer

    async with pool.acquire() as conn:
        tx = await _tenant_tx(conn, tenant_id)
        try:
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"soil-profile:{tenant_id}:{field_id}",
            )
            rows = await conn.fetch(
                """
                SELECT observation_id, contract_version, tenant_id::text, field_id, zone_id,
                       property, value_json, unit, depth_from_cm, depth_to_cm,
                       observed_at, received_at, source_type, source_id, procedure_id,
                       calibration_id, quality_status, quality_flags, confidence,
                       idempotency_key, provenance
                FROM soil_observations
                WHERE tenant_id=$1::uuid AND field_id=$2
                ORDER BY observed_at DESC
                LIMIT 5000
                """,
                tenant_id,
                field_id,
            )
            snapshot = profile_composer.compose_snapshot(
                tenant_id=tenant_id, field_id=field_id, observations=[dict(r) for r in rows]
            )
            payload = snapshot.model_dump(mode="json")
            await conn.execute(
                """
                INSERT INTO soil_profile_snapshots (
                    profile_id, profile_hash, contract_version, tenant_id, field_id, zone_id,
                    effective_at, data_available_at, status, evidence_level,
                    completeness_score, quality_passed, executable,
                    selection_policy_version, snapshot
                ) VALUES ($1,$2,$3,$4::uuid,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)
                ON CONFLICT (profile_hash) DO NOTHING
                """,
                snapshot.profile_id,
                snapshot.profile_hash,
                snapshot.contract_version,
                snapshot.tenant_id,
                snapshot.field_id,
                snapshot.zone_id,
                snapshot.effective_at,
                snapshot.data_available_at,
                snapshot.status.value,
                snapshot.evidence_level.value,
                snapshot.completeness_score,
                snapshot.quality_gate.passed,
                snapshot.quality_gate.executable,
                snapshot.selection_policy_version,
                json.dumps(payload),
            )
            await tx.commit()
            return snapshot
        except Exception:
            await tx.rollback()
            raise


async def canonical_sensor_readings(
    pool, *, tenant_id: str, field_id: str, limit: int = 100
) -> list[dict[str, Any]]:
    """Compatibility view built from the canonical observation store, not soil_readings."""
    rows = await list_observations(
        pool, tenant_id=tenant_id, field_id=field_id, limit=max(limit * 8, 100)
    )
    by_key: dict[tuple[str, Any], dict[str, Any]] = {}
    mapping = {
        "soil_temperature": "temperature",
        "soil_moisture": "moisture_pct",
        "ph": "ph_level",
        "ec": "ec_level",
        "electrical_conductivity": "ec_level",
        "nitrogen": "n_ppm",
        "phosphorus": "p_ppm",
        "potassium": "k_ppm",
    }
    for row in rows:
        target = mapping.get(row.get("property"))
        if not target or row.get("source_type") != "sensor":
            continue
        key = (row.get("source_id") or "unknown", row.get("observed_at"))
        item = by_key.setdefault(
            key,
            {
                "sensor_id": key[0],
                "recorded_at": key[1],
                "temperature": None,
                "moisture_pct": None,
                "ph_level": None,
                "ec_level": None,
                "n_ppm": None,
                "p_ppm": None,
                "k_ppm": None,
            },
        )
        item[target] = row.get("value_json")
    return sorted(by_key.values(), key=lambda x: x["recorded_at"], reverse=True)[:limit]
