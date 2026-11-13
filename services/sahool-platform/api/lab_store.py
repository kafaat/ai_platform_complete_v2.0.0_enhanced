"""Durable tenant-scoped laboratory persistence for soil and irrigation water."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def _sample_record(row):
    data = dict(row)
    if isinstance(data.get("sampling_origin"), str):
        data["sampling_origin"] = json.loads(data["sampling_origin"])
    return data


class SampleFieldNotFound(LookupError):
    """The requested field is outside the available tenant fields."""


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
          sampling_plan_id, barcode, collected_by, created_by, sampling_origin
        )
        SELECT $1,$2::uuid,f.field_id,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17::jsonb
        FROM fields f WHERE f.field_id=$3 AND f.tenant_id=$2::uuid
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
        json.dumps(payload["sampling_origin"]) if payload.get("sampling_origin") else None,
    )
    if row is None:
        raise SampleFieldNotFound(payload["field_id"])
    return _sample_record(row)


async def list_samples(
    conn, *, tenant_id: str, field_id: str | None = None, sample_id: str | None = None
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT s.* FROM lab_samples s
        JOIN fields f ON f.field_id=s.field_id AND f.tenant_id=s.tenant_id
        WHERE s.tenant_id=$1::uuid AND ($2::text IS NULL OR s.field_id=$2)
          AND ($3::text IS NULL OR s.sample_id=$3)
        ORDER BY s.created_at DESC
        """,
        tenant_id,
        field_id,
        sample_id,
    )
    return [_sample_record(r) for r in rows]


async def get_sample(conn, *, tenant_id: str, sample_id: str) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """SELECT s.* FROM lab_samples s
           JOIN fields f ON f.field_id=s.field_id AND f.tenant_id=s.tenant_id
           WHERE s.tenant_id=$1::uuid AND s.sample_id=$2 FOR UPDATE OF s""",
        tenant_id,
        sample_id,
    )
    return _sample_record(row) if row else None


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


class InvalidResultReplacement(ValueError):
    """A prior result cannot be superseded by the submitted measurement."""


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
                or prior["quality_status"] not in {"unreviewed", "approved"}
            ):
                raise InvalidResultReplacement("invalid_or_already_superseded_lab_result")
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


async def has_soil_result(conn, *, tenant_id: str, sample_id: str) -> bool:
    """Does this review cycle contain a result awaiting a review decision?"""
    row = await conn.fetchrow(
        """SELECT 1 FROM soil_lab_results
           WHERE tenant_id=$1::uuid AND sample_id=$2 AND quality_status='unreviewed'
           LIMIT 1""",
        tenant_id,
        sample_id,
    )
    return row is not None


async def reject_soil_results(conn, *, tenant_id: str, sample_id: str) -> None:
    """Reject pending measurements and restore the accepted parent of a declined correction."""
    await conn.execute(
        """WITH RECURSIVE rejected AS (
               UPDATE soil_lab_results SET quality_status='rejected'
               WHERE tenant_id=$1::uuid AND sample_id=$2 AND quality_status='unreviewed'
               RETURNING supersedes_result_id
           ), ancestors AS (
               SELECT supersedes_result_id AS result_id FROM rejected
               UNION
               SELECT r.supersedes_result_id
               FROM ancestors a JOIN soil_lab_results r ON r.result_id=a.result_id
               WHERE r.tenant_id=$1::uuid AND r.sample_id=$2
                 AND r.approved_at IS NULL AND r.published_observation_id IS NULL
           )
           UPDATE soil_lab_results r SET quality_status='approved'
           FROM ancestors a
           WHERE r.result_id=a.result_id AND r.tenant_id=$1::uuid AND r.sample_id=$2
             AND r.quality_status='superseded'
             AND (r.approved_at IS NOT NULL OR r.published_observation_id IS NOT NULL)""",
        tenant_id,
        sample_id,
    )


async def approve_soil_results(conn, *, tenant_id: str, sample_id: str, approved_by: str) -> int:
    """يَختِم صفوف نتيجة التربة غير المُعتمَدة بالاعتماد + هويّة المُعتمِد + طابع زمنيّ.

    نقطة ختم الاعتماد الوحيدة: تُستدعى فقط من انتقال الحالة المُصرَّح به (→ approved)،
    فتُصبح النتائج مؤهّلة للاستهلاك في القرار (latest_soil_analysis/publishable). لا تلمس
    الصفوف المُلغاة (superseded) ولا المُعتمَدة مسبقاً. تُرجِع عدد الصفوف المختومة.
    """
    result = await conn.execute(
        """UPDATE soil_lab_results
           SET quality_status='approved', approved_by=$3, approved_at=$4
           WHERE tenant_id=$1::uuid AND sample_id=$2 AND quality_status='unreviewed'""",
        tenant_id,
        sample_id,
        approved_by,
        datetime.now(UTC),
    )
    # asyncpg execute → "UPDATE N"؛ نُخرِج N عدداً (best-effort، 0 إن لا صفوف مؤهّلة).
    try:
        return int(str(result).split()[-1])
    except (ValueError, IndexError):
        return 0


def _analyte_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


async def latest_soil_analysis(
    conn, *, tenant_id: str, field_id: str, sample_id: str | None = None
) -> dict[str, Any] | None:
    rows = await conn.fetch(
        """
        SELECT s.sample_id, r.result_id, r.analyte, r.value_json, r.method_code, r.quality_status, r.published_observation_id, r.supersedes_result_id
        FROM lab_samples s JOIN soil_lab_results r ON r.sample_id=s.sample_id AND r.tenant_id=s.tenant_id
        JOIN fields f ON f.field_id=s.field_id AND f.tenant_id=s.tenant_id
        WHERE s.tenant_id=$1::uuid AND s.field_id=$2 AND s.kind='soil'
          AND ($3::text IS NULL OR s.sample_id=$3)
          AND s.status IN ('approved','published')
          AND r.quality_status='approved'
        ORDER BY s.created_at DESC, s.sample_id, r.observed_at DESC, r.received_at DESC, r.result_id DESC
        """,
        tenant_id,
        field_id,
        sample_id,
    )
    if not rows:
        return None
    sid = rows[0]["sample_id"]
    values = {}
    for row in rows:
        if row["sample_id"] == sid:
            if row["analyte"] == "ec_dsm":
                values.setdefault("ec_extraction_method", row.get("method_code"))
            values.setdefault(row["analyte"], _analyte_value(row["value_json"]))
    values.update({"sample_id": sid, "approved": True})
    return values


# Lab review cycle (the delivery's api/lab_review.py, folded here so the platform module
# count stays within its budget): who entered the current cycle's results, and which
# measurements a reviewer is shown and must name when approving.
async def result_entry_actors(conn, tenant_id: str, sample_id: str) -> set[str]:
    rows = await conn.fetch(
        """SELECT DISTINCT actor_id FROM lab_sample_custody_events
           WHERE tenant_id=$1::uuid AND sample_id=$2 AND event_type='lab_result_received'
             AND occurred_at > COALESCE((
                 SELECT MAX(occurred_at) FROM lab_sample_custody_events
                 WHERE tenant_id=$1::uuid AND sample_id=$2 AND event_type IN ('status:approved', 'status:rejected')
             ), '-infinity'::timestamptz)""",
        tenant_id,
        sample_id,
    )
    return {r["actor_id"] for r in rows if r["actor_id"]}


async def review_results(conn, tenant_id: str, sample_id: str) -> list[dict]:
    rows = await conn.fetch(
        """SELECT result_id, analyte, value_json, unit, method_code, observed_at, quality_status
           FROM soil_lab_results WHERE tenant_id=$1::uuid AND sample_id=$2
             AND quality_status IN ('approved','unreviewed')
           ORDER BY analyte, observed_at DESC, result_id""",
        tenant_id,
        sample_id,
    )
    return [{**dict(row), "value_json": _analyte_value(row["value_json"])} for row in rows]


class WaterResultRefused(Exception):
    """A water result submission the sample's state or history does not allow."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


_WATER_LIVE = ("unreviewed", "approved")


def _water_reply(row) -> dict[str, Any]:
    analysis = row["analysis"]
    analysis = json.loads(analysis) if isinstance(analysis, str) else dict(analysis)
    prior = row["supersedes_result_set_id"]
    return {
        **analysis,
        "result_id": str(row["result_set_id"]),
        "supersedes_result_id": str(prior) if prior else None,
        "quality_status": row["quality_status"],
    }


async def record_water_result(
    conn,
    *,
    tenant_id: str,
    actor_id: str,
    sample_id: str,
    payload: dict[str, Any],
    analysis: dict[str, Any],
    observed_at: datetime,
    request_digest: str,
    supersedes: str | None = None,
    correction_reason: str | None = None,
) -> dict[str, Any]:
    """Store one water measurement set under the sample's row lock.

    The live set (unreviewed or approved) is the sample's one current result. The same
    measurement again returns that row, so a lost response, a retry without a key and two
    concurrent submits all leave one stored result. A different measurement must name the
    live set it corrects; the corrected set keeps its approval and publication stamps.
    """
    from core.engines.soil_lab_workflow import SoilWorkflowError, validate_soil_transition

    sample = await get_sample(conn, tenant_id=tenant_id, sample_id=sample_id)
    if not sample or sample["kind"] != "water":
        raise WaterResultRefused(404, "water sample not found")
    live = await conn.fetchrow(
        """SELECT * FROM water_lab_result_sets
           WHERE tenant_id=$1::uuid AND sample_id=$2 AND quality_status = ANY($3::text[])
           ORDER BY created_at DESC LIMIT 1""",
        tenant_id,
        sample_id,
        list(_WATER_LIVE),
    )
    if live is not None and live["request_digest"] == request_digest:
        return _water_reply(live)
    if live is not None and str(live["result_set_id"]) != (supersedes or ""):
        raise WaterResultRefused(
            409, "a result is already recorded; a correction must name it as supersedes_result_id"
        )
    if live is None and supersedes:
        raise WaterResultRefused(409, "superseded result must be the current result of the sample")
    status = sample["status"]
    if not supersedes:
        if status == "sampled":
            await set_status(conn, tenant_id=tenant_id, sample_id=sample_id, status="in_lab")
            status = "in_lab"
        try:
            validate_soil_transition(status, "result_received", has_result=True)
        except SoilWorkflowError as exc:
            raise WaterResultRefused(exc.http_status, exc.message_ar) from exc
    elif status not in {"result_received", "approved", "published"}:
        raise WaterResultRefused(409, f"a {status} sample cannot take a correction")
    row = await conn.fetchrow(
        """INSERT INTO water_lab_result_sets
           (result_set_id,tenant_id,sample_id,payload,analysis,quality_status,observed_at,
            supersedes_result_set_id,request_digest,correction_reason,entered_by)
           VALUES($1,$2::uuid,$3,$4::jsonb,$5::jsonb,'unreviewed',$6,$7::uuid,$8,$9,$10)
           RETURNING *""",
        uuid4(),
        tenant_id,
        sample_id,
        json.dumps(payload),
        json.dumps(analysis),
        observed_at,
        supersedes,
        request_digest,
        correction_reason,
        actor_id,
    )
    if supersedes:
        await conn.execute(
            """UPDATE water_lab_result_sets SET quality_status='superseded'
               WHERE tenant_id=$1::uuid AND result_set_id=$2::uuid""",
            tenant_id,
            supersedes,
        )
    await set_status(conn, tenant_id=tenant_id, sample_id=sample_id, status="result_received")
    await add_custody_event(
        conn,
        tenant_id=tenant_id,
        sample_id=sample_id,
        actor_id=actor_id,
        event_type="lab_result_received",
        condition_notes=(
            f"correction of {supersedes}: {correction_reason or ''}" if supersedes else None
        ),
    )
    return _water_reply(row)


async def water_review_results(conn, tenant_id: str, sample_id: str) -> list[dict]:
    """The live water set a reviewer is shown and must name, in the soil review's shape."""
    rows = await conn.fetch(
        """SELECT result_set_id, payload, observed_at, quality_status, supersedes_result_set_id
           FROM water_lab_result_sets WHERE tenant_id=$1::uuid AND sample_id=$2
             AND quality_status IN ('approved','unreviewed')
           ORDER BY observed_at DESC, result_set_id""",
        tenant_id,
        sample_id,
    )
    return [
        {
            "result_id": r["result_set_id"],
            "analyte": "irrigation_water",
            "value_json": _analyte_value(r["payload"]),
            "unit": None,
            "method_code": None,
            "observed_at": r["observed_at"],
            "quality_status": r["quality_status"],
            "supersedes_result_id": r["supersedes_result_set_id"],
        }
        for r in rows
    ]


async def has_water_result(conn, *, tenant_id: str, sample_id: str, quality: str) -> bool:
    row = await conn.fetchrow(
        """SELECT 1 FROM water_lab_result_sets
           WHERE tenant_id=$1::uuid AND sample_id=$2 AND quality_status=$3 LIMIT 1""",
        tenant_id,
        sample_id,
        quality,
    )
    return row is not None


async def seal_water_review(
    conn, *, tenant_id: str, sample_id: str, target: str, actor_id: str, result_ids: list | None
) -> None:
    """Apply a review transition to the sample's water sets.

    Approval seals only the named sets that still await review. Rejection declines the
    pending set and restores the approved or published set it would have replaced.
    Publication stamps the approved set; the stamp of an earlier publication is kept."""
    if target == "approved":
        await conn.execute(
            """UPDATE water_lab_result_sets
               SET quality_status='approved', approved_by=$3, approved_at=now()
               WHERE tenant_id=$1::uuid AND sample_id=$2 AND quality_status='unreviewed'
                 AND result_set_id = ANY($4::uuid[])""",
            tenant_id,
            sample_id,
            actor_id,
            [str(i) for i in result_ids or []],
        )
    elif target == "rejected":
        await conn.execute(
            """WITH rejected AS (
                   UPDATE water_lab_result_sets SET quality_status='rejected'
                   WHERE tenant_id=$1::uuid AND sample_id=$2 AND quality_status='unreviewed'
                   RETURNING supersedes_result_set_id
               )
               UPDATE water_lab_result_sets w SET quality_status='approved'
               FROM rejected r
               WHERE w.result_set_id=r.supersedes_result_set_id AND w.tenant_id=$1::uuid
                 AND w.quality_status='superseded' AND w.approved_at IS NOT NULL""",
            tenant_id,
            sample_id,
        )
    elif target == "published":
        await conn.execute(
            """UPDATE water_lab_result_sets SET published_at=now()
               WHERE tenant_id=$1::uuid AND sample_id=$2 AND quality_status='approved'
                 AND published_at IS NULL""",
            tenant_id,
            sample_id,
        )


async def latest_water_analysis(conn, *, tenant_id: str, field_id: str) -> dict[str, Any] | None:
    """The newest reviewed water analysis of the field; a pending set is not a decision input."""
    row = await conn.fetchrow(
        """SELECT w.analysis FROM lab_samples s JOIN water_lab_result_sets w
           ON w.sample_id=s.sample_id AND w.tenant_id=s.tenant_id
           JOIN fields f ON f.field_id=s.field_id AND f.tenant_id=s.tenant_id
           WHERE s.tenant_id=$1::uuid AND s.field_id=$2 AND s.kind='water'
             AND s.status IN ('approved','published') AND w.quality_status='approved'
           ORDER BY w.observed_at DESC LIMIT 1""",
        tenant_id,
        field_id,
    )
    if not row:
        return None
    analysis = row["analysis"]
    return json.loads(analysis) if isinstance(analysis, str) else dict(analysis)


async def publishable_soil_results(conn, *, tenant_id: str, sample_id: str) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """SELECT DISTINCT ON (r.analyte) r.result_id, r.analyte, r.value_json, r.unit, r.method_code, r.detection_limit,
                         r.uncertainty, r.observed_at, r.supersedes_result_id, r.published_observation_id,
                         prior.published_observation_id AS superseded_published_observation_id
                  FROM soil_lab_results r
                  LEFT JOIN soil_lab_results prior ON prior.result_id=r.supersedes_result_id
                  WHERE r.tenant_id=$1::uuid AND r.sample_id=$2 AND r.quality_status='approved'
                  ORDER BY r.analyte, r.observed_at DESC, r.received_at DESC, r.result_id DESC""",
        tenant_id,
        sample_id,
    )
    return [dict(r, value_json=_analyte_value(r["value_json"])) for r in rows]


async def current_soil_result_ids(
    conn, *, tenant_id: str, sample_id: str, analytes: list[str]
) -> dict[str, Any]:
    """The newest result per analyte of this sample that no correction has superseded.

    A rejected row is not current: insert_soil_results refuses to supersede it."""
    rows = await conn.fetch(
        """SELECT DISTINCT ON (analyte) analyte, result_id FROM soil_lab_results
           WHERE tenant_id=$1::uuid AND sample_id=$2 AND analyte = ANY($3::text[])
             AND quality_status IN ('unreviewed', 'approved')
           ORDER BY analyte, observed_at DESC, received_at DESC, result_id DESC""",
        tenant_id,
        sample_id,
        analytes,
    )
    return {r["analyte"]: r["result_id"] for r in rows}


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
                   WHERE tenant_id=$1::uuid AND result_id=$2::uuid
                     AND published_observation_id IS DISTINCT FROM $3""",
                tenant_id,
                result_id,
                observation_id,
            )


# Soil-sampling plan copies (v258). The AI planner's plan reaches the platform through the
# service-authenticated advice event; a sample that names a plan point is then resolved from
# this copy, never from the coordinates, zone or imagery the client sends with it.
ON_PLAN_TOLERANCE_M = 30.0
_SPECTRAL = ("ndvi", "ndmi", "reci", "msavi")


async def save_sampling_plan_copies(
    conn, *, tenant_id: str, field_id: str, plans: list[dict[str, Any]], source: str
) -> int:
    stored = 0
    for item in plans:
        plan, points = item.get("plan"), item.get("sample_points")
        plan_id = plan.get("plan_id") if isinstance(plan, dict) else None
        if (
            item.get("field_id") != field_id
            or not isinstance(plan_id, str)
            or not 0 < len(plan_id) <= 64
            or not isinstance(points, list)
            or not points
            or not all(isinstance(p, dict) for p in points)
        ):
            continue
        status = await conn.execute(
            """INSERT INTO soil_sampling_plan_copies
               (tenant_id, plan_id, field_id, plan, sample_points, source)
               VALUES ($1::uuid, $2, $3, $4::jsonb, $5::jsonb, $6)
               ON CONFLICT (tenant_id, plan_id) DO NOTHING""",
            tenant_id,
            plan_id,
            field_id,
            json.dumps(plan),
            json.dumps(points),
            source,
        )
        stored += str(status).endswith(" 1")
    return stored


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6_371_008.8 * asin(sqrt(h))


async def _layer_status(conn, tenant_id: str, field_id: str, name: str, source: Any) -> str:
    """A layer is verified only by a registered raster asset of this tenant and field."""
    if not isinstance(source, dict):
        return "unverified"
    if name == "slope":
        query = """SELECT 1 FROM raster_assets WHERE tenant_id=$1::uuid AND field_id=$2
                   AND lower(index_name) IN ('slope','dem','terrain','elevation')
                   AND (id::text=$3 OR scene_id=$3 OR cog_uri=$3) LIMIT 1"""
        args = [source.get("asset_id")]
    elif name in _SPECTRAL:
        query = """SELECT 1 FROM raster_assets WHERE tenant_id=$1::uuid AND field_id=$2
                   AND scene_id=$3 AND acquisition_date=$4::date AND lower(index_name)=$5 LIMIT 1"""
        try:
            day = datetime.fromisoformat(str(source.get("acquisition_date"))[:10]).date()
        except ValueError:
            return "unverified"
        args = [source.get("scene_id"), day, name]
    else:
        return "unverified"
    if not isinstance(args[0], str) or not args[0].strip():
        return "unverified"
    row = await conn.fetchrow(query, tenant_id, field_id, *args)
    return "verified" if row else "unverified"


def _stored_point(points: Any, point_id: str) -> dict[str, Any] | None:
    if isinstance(points, str):
        points = json.loads(points)
    for point in points if isinstance(points, list) else []:
        coords = (point.get("point") or {}).get("coordinates") if isinstance(point, dict) else None
        if (
            point.get("sample_id") == point_id
            and isinstance(coords, list)
            and len(coords) == 2
            and all(isinstance(c, int | float) and not isinstance(c, bool) for c in coords)
        ):
            return point
    return None


async def resolve_sampling_origin(
    conn,
    *,
    tenant_id: str,
    field_id: str,
    plan_id: str,
    claimed: dict[str, Any],
    latitude: float,
    longitude: float,
    gps_accuracy_m: float | None,
    deviation_reason: str | None,
) -> dict[str, Any]:
    """The origin recorded with a plan-point sample.

    With the plan stored and the point in it, the planned position, zone, depth, purpose and
    indicator layers come from the stored copy, and each layer is checked against the raster
    registry. Otherwise the client's claim is kept as a claim and marked unverified. The
    collection position and its distance from the planned point are recorded either way."""
    row = await conn.fetchrow(
        """SELECT sample_points FROM soil_sampling_plan_copies
           WHERE tenant_id=$1::uuid AND plan_id=$2 AND field_id=$3""",
        tenant_id,
        plan_id,
        field_id,
    )
    point = _stored_point(row["sample_points"], claimed["point_id"]) if row else None
    mismatch: list[str] = []
    if point is None:
        origin = dict(claimed)
        layers = {name: "unverified" for name in origin.get("indicator_sources") or {}}
    else:
        lon, lat = point["point"]["coordinates"]
        depth = point.get("depth_cm")
        origin = {
            "point_id": claimed["point_id"],
            "zone_id": point.get("zone_id"),
            "latitude": lat,
            "longitude": lon,
            "location_id": point.get("location_id"),
            "composite": point.get("composite"),
            "sampling_purpose": point.get("sampling_purpose"),
            "planned_depth_cm": depth if isinstance(depth, list) and len(depth) == 2 else None,
            "indicators": [i for i in point.get("indicators") or [] if isinstance(i, str)],
            "indicator_sources": point.get("indicator_sources") or {},
        }
        origin = {k: v for k, v in origin.items() if v is not None}
        mismatch = sorted(
            key
            for key in ("zone_id", "latitude", "longitude", "indicators", "indicator_sources")
            if claimed.get(key) not in (None, [], {}) and claimed.get(key) != origin.get(key)
        )
        has_registry = await conn.fetchval("SELECT to_regclass('raster_assets') IS NOT NULL")
        layers = {}
        for name, source in origin["indicator_sources"].items():
            layers[name] = (
                await _layer_status(conn, tenant_id, field_id, name, source)
                if has_registry
                else "unverified"
            )
    unverified = [i for i in origin.get("indicators") or [] if layers.get(i) != "verified"]
    unverified += [
        name for name, state in layers.items() if state != "verified" and name not in unverified
    ]
    deviation = _distance_m(origin["latitude"], origin["longitude"], latitude, longitude)
    tolerance = ON_PLAN_TOLERANCE_M + float(gps_accuracy_m or 0)
    origin.update(
        plan_verification=(
            "stored_plan" if point else "point_not_in_plan" if row else "plan_not_stored"
        ),
        layer_verification=layers,
        unverified_indicators=unverified,
        client_claim_mismatch=mismatch,
        verification="documented" if point is not None and not unverified else "unverified",
        collection={
            "latitude": latitude,
            "longitude": longitude,
            "deviation_m": round(deviation, 1),
            "tolerance_m": tolerance,
            "on_plan": deviation <= tolerance,
            "deviation_reason": deviation_reason,
        },
    )
    return origin
