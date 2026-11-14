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


_WATER_SET_COLUMNS = """result_set_id, sample_id, payload, analysis, quality_status, observed_at,
           approved_by, approved_at, published_at, supersedes_result_set_id, request_digest,
           entered_by"""


async def live_water_sets(conn, *, tenant_id: str) -> list:
    """Every live (unreviewed or approved) water set of the tenant, for an operator recompute."""
    return await conn.fetch(
        f"""SELECT {_WATER_SET_COLUMNS} FROM water_lab_result_sets
           WHERE tenant_id=$1::uuid AND quality_status = ANY($2::text[])
           ORDER BY sample_id, created_at""",
        tenant_id,
        list(_WATER_LIVE),
    )


async def append_water_analysis_revision(
    conn, *, tenant_id: str, seen, analysis: dict[str, Any], reason: str
) -> str | None:
    """Replace a live set's derived analysis by a v258 revision; the measurement is unchanged.

    ``seen`` is the set as the caller read it. Under the sample's row lock (the order of
    ``record_water_result``) the set is read again; if a submit or review changed it since,
    nothing is written and None is returned. Otherwise a new row supersedes it with the same
    payload, review state, approval and publication stamps, author and request digest (a retry of
    the original measurement still returns the current row), ``analysis`` and
    ``correction_reason=reason``; the replaced row becomes superseded and keeps everything it
    had. No custody event: a recompute is not a lab result, and the review's separation of
    duties stays as it was.
    """
    if await get_sample(conn, tenant_id=tenant_id, sample_id=seen["sample_id"]) is None:
        return None
    current = await conn.fetchrow(
        f"""SELECT {_WATER_SET_COLUMNS} FROM water_lab_result_sets
           WHERE tenant_id=$1::uuid AND result_set_id=$2::uuid
             AND quality_status = ANY($3::text[]) FOR UPDATE""",
        tenant_id,
        str(seen["result_set_id"]),
        list(_WATER_LIVE),
    )
    if (
        current is None
        or current["quality_status"] != seen["quality_status"]
        or _json_value(current["analysis"]) != _json_value(seen["analysis"])
    ):
        return None
    revision_id = uuid4()
    await conn.execute(
        """INSERT INTO water_lab_result_sets
           (result_set_id, tenant_id, sample_id, payload, analysis, quality_status, observed_at,
            approved_by, approved_at, published_at, supersedes_result_set_id, request_digest,
            correction_reason, entered_by)
           VALUES ($1, $2::uuid, $3, $4::jsonb, $5::jsonb, $6, $7, $8, $9, $10, $11::uuid, $12,
                   $13, $14)""",
        revision_id,
        tenant_id,
        current["sample_id"],
        json.dumps(_json_value(current["payload"])),
        json.dumps(analysis),
        current["quality_status"],
        current["observed_at"],
        current["approved_by"],
        current["approved_at"],
        current["published_at"],
        str(current["result_set_id"]),
        current["request_digest"],
        reason,
        current["entered_by"],
    )
    await conn.execute(
        """UPDATE water_lab_result_sets SET quality_status='superseded'
           WHERE tenant_id=$1::uuid AND result_set_id=$2::uuid""",
        tenant_id,
        str(current["result_set_id"]),
    )
    return str(revision_id)


def _json_value(value):
    return json.loads(value) if isinstance(value, str) else dict(value)


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
