"""Durable tenant-scoped laboratory persistence for soil and irrigation water."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


async def create_sample(
    conn, *, tenant_id: str, created_by: str, payload: dict[str, Any]
) -> dict[str, Any]:
    sample_id = f"{payload['kind'][:1]}-{uuid4().hex[:10]}"
    status = payload.get("status") or "sampled"
    row = await conn.fetchrow(
        """
        INSERT INTO lab_samples (
          sample_id, tenant_id, field_id, kind, latitude, longitude, sampled_on,
          depth_cm_from, depth_cm_to, source, status, gps_accuracy_m,
          sampling_plan_id, barcode, collected_by, created_by
        ) VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
        RETURNING *
        """,
        sample_id,
        tenant_id,
        payload["field_id"],
        payload["kind"],
        payload["latitude"],
        payload["longitude"],
        payload.get("sampled_on"),
        payload.get("depth_cm_from"),
        payload.get("depth_cm_to"),
        payload.get("source"),
        status,
        payload.get("gps_accuracy_m"),
        payload.get("sampling_plan_id"),
        payload.get("barcode"),
        payload.get("collected_by"),
        created_by,
    )
    return dict(row)


async def list_samples(
    conn, *, tenant_id: str, field_id: str | None = None
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT * FROM lab_samples
        WHERE tenant_id=$1::uuid AND ($2::text IS NULL OR field_id=$2)
        ORDER BY created_at DESC
        """,
        tenant_id,
        field_id,
    )
    return [dict(r) for r in rows]


async def get_sample(conn, *, tenant_id: str, sample_id: str) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        "SELECT * FROM lab_samples WHERE tenant_id=$1::uuid AND sample_id=$2",
        tenant_id,
        sample_id,
    )
    return dict(row) if row else None


async def set_status(conn, *, tenant_id: str, sample_id: str, status: str) -> dict[str, Any]:
    row = await conn.fetchrow(
        """UPDATE lab_samples SET status=$3, updated_at=now()
           WHERE tenant_id=$1::uuid AND sample_id=$2 RETURNING *""",
        tenant_id,
        sample_id,
        status,
    )
    if not row:
        raise KeyError(sample_id)
    return dict(row)


async def add_custody_event(
    conn,
    *,
    tenant_id: str,
    sample_id: str,
    actor_id: str,
    event_type: str,
    occurred_at: datetime | None = None,
    location: str | None = None,
    condition_notes: str | None = None,
    seal_id: str | None = None,
) -> dict[str, Any]:
    event_id = uuid4()
    row = await conn.fetchrow(
        """INSERT INTO lab_sample_custody_events
           (event_id,tenant_id,sample_id,event_type,occurred_at,actor_id,location,condition_notes,seal_id)
           VALUES($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9) RETURNING *""",
        event_id,
        tenant_id,
        sample_id,
        event_type,
        occurred_at or datetime.now(UTC),
        actor_id,
        location,
        condition_notes,
        seal_id,
    )
    return dict(row)


async def insert_soil_results(
    conn,
    *,
    tenant_id: str,
    sample_id: str,
    analytes: list[dict[str, Any]],
    observed_at: datetime,
    approved: bool,
    approved_by: str | None,
    correction_reason: str | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    quality = "approved" if approved else "unreviewed"
    for item in analytes:
        supersedes = item.get("supersedes_result_id")
        if supersedes:
            prior = await conn.fetchrow(
                """SELECT result_id, analyte, quality_status, published_observation_id
                   FROM soil_lab_results
                   WHERE tenant_id=$1::uuid AND sample_id=$2 AND result_id=$3
                   FOR UPDATE""",
                tenant_id,
                sample_id,
                supersedes,
            )
            if (
                not prior
                or prior["analyte"] != item["analyte"]
                or prior["quality_status"] == "superseded"
            ):
                raise ValueError("invalid_or_already_superseded_lab_result")
        row = await conn.fetchrow(
            """INSERT INTO soil_lab_results
               (result_id,tenant_id,sample_id,analyte,value_json,unit,method_code,detection_limit,
                uncertainty,quality_status,observed_at,approved_by,approved_at,supersedes_result_id)
               VALUES($1,$2::uuid,$3,$4,$5::jsonb,$6,$7,$8,$9,$10,$11,$12,$13,$14) RETURNING *""",
            uuid4(),
            tenant_id,
            sample_id,
            item["analyte"],
            json.dumps(item["value"]),
            item.get("unit"),
            item.get("method_code"),
            item.get("detection_limit"),
            item.get("uncertainty"),
            quality,
            observed_at,
            approved_by if approved else None,
            datetime.now(UTC) if approved else None,
            supersedes,
        )
        if supersedes:
            await conn.execute(
                """UPDATE soil_lab_results SET quality_status='superseded'
                   WHERE tenant_id=$1::uuid AND result_id=$2""",
                tenant_id,
                supersedes,
            )
        out.append(dict(row))
    return out


async def latest_soil_analysis(conn, *, tenant_id: str, field_id: str) -> dict[str, Any] | None:
    rows = await conn.fetch(
        """
        SELECT s.sample_id, r.result_id, r.analyte, r.value_json, r.quality_status, r.published_observation_id, r.supersedes_result_id
        FROM lab_samples s JOIN soil_lab_results r ON r.sample_id=s.sample_id AND r.tenant_id=s.tenant_id
        WHERE s.tenant_id=$1::uuid AND s.field_id=$2 AND s.kind='soil'
          AND s.status IN ('approved','published')
          AND r.quality_status='approved'
        ORDER BY s.created_at DESC, r.observed_at DESC
        """,
        tenant_id,
        field_id,
    )
    if not rows:
        return None
    sid = rows[0]["sample_id"]
    values = {r["analyte"]: r["value_json"] for r in rows if r["sample_id"] == sid}
    values.update({"sample_id": sid, "approved": True})
    return values


async def insert_water_result(
    conn,
    *,
    tenant_id: str,
    sample_id: str,
    payload: dict[str, Any],
    analysis: dict[str, Any],
    observed_at: datetime,
    approved_by: str | None = None,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """INSERT INTO water_lab_result_sets
           (result_set_id,tenant_id,sample_id,payload,analysis,quality_status,observed_at,approved_by,approved_at)
           VALUES($1,$2::uuid,$3,$4::jsonb,$5::jsonb,$6,$7,$8,$9) RETURNING *""",
        uuid4(),
        tenant_id,
        sample_id,
        json.dumps(payload),
        json.dumps(analysis),
        "approved" if approved_by else "unreviewed",
        observed_at,
        approved_by,
        datetime.now(UTC) if approved_by else None,
    )
    return dict(row)


async def latest_water_analysis(conn, *, tenant_id: str, field_id: str) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """SELECT w.analysis FROM lab_samples s JOIN water_lab_result_sets w
           ON w.sample_id=s.sample_id AND w.tenant_id=s.tenant_id
           WHERE s.tenant_id=$1::uuid AND s.field_id=$2 AND s.kind='water'
           ORDER BY w.observed_at DESC LIMIT 1""",
        tenant_id,
        field_id,
    )
    return dict(row["analysis"]) if row else None


async def publishable_soil_results(conn, *, tenant_id: str, sample_id: str) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """SELECT r.result_id, r.analyte, r.value_json, r.unit, r.method_code, r.detection_limit,
                         r.uncertainty, r.observed_at, r.supersedes_result_id, r.published_observation_id,
                         prior.published_observation_id AS superseded_published_observation_id
                  FROM soil_lab_results r
                  LEFT JOIN soil_lab_results prior ON prior.result_id=r.supersedes_result_id
                  WHERE r.tenant_id=$1::uuid AND r.sample_id=$2 AND r.quality_status='approved'
                  ORDER BY r.analyte, r.received_at DESC""",
        tenant_id,
        sample_id,
    )
    return [dict(r) for r in rows]


async def mark_soil_results_published(
    conn,
    *,
    tenant_id: str,
    observation_by_analyte: dict[str, str],
    result_by_analyte: dict[str, str],
) -> None:
    for analyte, observation_id in observation_by_analyte.items():
        result_id = result_by_analyte.get(analyte)
        if result_id:
            await conn.execute(
                """UPDATE soil_lab_results
                   SET published_observation_id=$3, published_at=now()
                   WHERE tenant_id=$1::uuid AND result_id=$2::uuid""",
                tenant_id,
                result_id,
                observation_id,
            )
