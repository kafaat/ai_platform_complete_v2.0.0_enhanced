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


async def latest_soil_4r_rows(conn, *, tenant_id: str, field_id: str) -> list:
    """Read one approved sample and its current results together under tenant RLS."""
    return await conn.fetch(
        """WITH sample AS (
               SELECT s.sample_id, s.tenant_id, s.sampled_on, s.sampling_origin
               FROM lab_samples s
               WHERE s.tenant_id=$1::uuid AND s.field_id=$2 AND s.kind='soil'
                 AND s.status IN ('approved','published')
                 AND COALESCE(s.sampled_on, s.created_at::date) <= CURRENT_DATE
               ORDER BY COALESCE(s.sampled_on, s.created_at::date) DESC,
                        s.created_at DESC, s.sample_id DESC LIMIT 1
           )
           SELECT DISTINCT ON (r.analyte) s.sample_id, s.sampled_on,
                  s.sampling_origin->>'zone_id' AS zone_id,
                  r.analyte, r.result_id, r.unit, r.value_json, r.method_code,
                  r.quality_status, r.approved_at
           FROM sample s JOIN soil_lab_results r
             ON r.tenant_id=s.tenant_id AND r.sample_id=s.sample_id
           WHERE r.quality_status='approved' AND r.observed_at<=now()
           ORDER BY r.analyte, r.observed_at DESC, r.received_at DESC, r.result_id DESC""",
        tenant_id,
        field_id,
    )


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def approved_soil_lab_block(field_id: str, tenant_id: str, rows) -> dict[str, Any]:
    """The owner's approved soil lab result as the advisor's ``approved_soil_lab`` block.

    ``rows`` come from ``latest_soil_4r_rows`` (the read the field 4R plan uses). Values are
    passed through as stored, each with its method, unit, sampling date and approval
    reference; a row without a ``result_id``, not approved, or without a usable value is
    left out. No approved row ⇒ ``status="unavailable"`` with no results.
    """
    results = []
    for row in rows or ():
        row = dict(row)
        result_id = row.get("result_id")
        if not result_id or row.get("quality_status") != "approved":
            continue
        value = usable_analyte_value(row.get("analyte"), _analyte_value(row.get("value_json")))
        if value is None:
            continue
        record = {
            "result_id": str(result_id),
            "analyte": row.get("analyte"),
            "value": value,
            "unit": row.get("unit"),
            "method_code": row.get("method_code"),
            "quality_status": "approved",
            "sample_id": row.get("sample_id"),
            "sampled_on": _iso(row.get("sampled_on")),
            "approved_at": _iso(row.get("approved_at")),
            "approval_ref": f"{SOIL_LAB_CANONICAL_SOURCE}:{result_id}",
        }
        if row.get("zone_id"):
            record["zone_id"] = row["zone_id"]
        results.append(record)
    return {
        "owner": "sahool-platform",
        "source": SOIL_LAB_CANONICAL_SOURCE,
        "field_id": field_id,
        "tenant_id": tenant_id,
        "status": "available" if results else "unavailable",
        "reason": None if results else "no_approved_soil_lab_result",
        "results": results,
    }


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


def soil_result_analytes(payload) -> list[dict]:
    """One row per analyte present in a ``SoilLabResultIn`` (unit, method, supersession)."""
    units = {
        "ph": "1",
        "ec_dsm": "dS/m",
        "organic_matter_pct": "%",
        "nitrogen_mg_kg": "mg/kg",
        "phosphorus_mg_kg": "mg/kg",
        "potassium_mg_kg": "mg/kg",
        "cec_cmol_kg": "cmol(+)/kg",
        "calcium_carbonate_pct": "%",
        "sand_pct": "%",
        "silt_pct": "%",
        "clay_pct": "%",
        "texture": None,
    }
    out = []
    for name, unit in units.items():
        value = getattr(payload, name)
        if value is not None:
            out.append(
                {
                    "analyte": name,
                    "value": value,
                    "unit": unit,
                    "method_code": (
                        payload.ec_extraction_method or payload.method_code
                        if name == "ec_dsm"
                        else payload.method_code
                    ),
                    "detection_limit": payload.detection_limit,
                    "uncertainty": payload.uncertainty,
                    "supersedes_result_id": payload.supersedes_result_ids.get(name),
                }
            )
    return out


# Sand, silt and clay are validated together and texture is derived from them, so a
# correction resends the whole group. Each resent member supersedes its current row;
# otherwise the unchanged fractions and the new texture reuse the old idempotency key
# in soil-service with a different value/time (409) and the old texture stays approved.
TEXTURE_GROUP = ("sand_pct", "silt_pct", "clay_pct", "texture")


async def link_texture_group(conn, tenant_id: str, sample_id: str, analytes: list[dict]) -> None:
    unlinked = [
        a["analyte"]
        for a in analytes
        if a["analyte"] in TEXTURE_GROUP and not a.get("supersedes_result_id")
    ]
    if not unlinked:
        return
    current = await current_soil_result_ids(
        conn, tenant_id=tenant_id, sample_id=sample_id, analytes=unlinked
    )
    for item in analytes:
        if item["analyte"] in current and not item.get("supersedes_result_id"):
            item["supersedes_result_id"] = current[item["analyte"]]


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


# ─── W1-03: soil_lab_results is the single canonical soil-lab store ─────────────────────
# Owner decision 2026-11-16: platform readers of a field's soil analysis go through the
# helpers below. They return approved v156 results (with their result_ids) and fall back to
# the frozen legacy ``soil_lab_tests`` table only as a labelled source; nothing else in the
# platform reads that table. Eligibility is that of ``soil_enrichment.latest_lab_texture_row``
# (an approved result stays eligible while its sample is reopened for another analyte's
# correction; a rejected/cancelled sample withdraws it), and both sources need a collection
# date that is not in the future. The newest collection date wins; on a tie, v156 wins.
#
# Collection date: ``/api/v1/lab/samples`` accepts a sample without ``sampled_on``, so a row
# without one is dated by when it was registered (``lab_samples.created_at`` /
# ``soil_lab_tests.created_at``) — never later than the collection it records, so freshness
# is never overstated — and says so in ``sampled_on_source``. Dropping it would hide an
# approved analysis from every reader while lab-context shows it.
#
# EC: a v156 ``ec_dsm`` is an ECe (saturated paste) only when its method says so. EC 1:1,
# 1:2.5, 1:5 or unspecified readings are not comparable with the ECe salinity thresholds
# (``_interpret_lab_values``, ``LAB_EC_PROPERTIES_BY_METHOD``), so they never come back as
# ``ec_dsm``; the analysis carries them labelled in ``ec_other_extract`` instead.
SOIL_LAB_CANONICAL_SOURCE = "soil_lab_results"
SOIL_LAB_LEGACY_SOURCE = "legacy_soil_lab_tests"
ECE_EXTRACTION_METHOD = "saturated_paste"

# Keys a free-form legacy ``soil_lab_tests.result`` may use for a v156 analyte — the union of
# what the migrated readers accepted (field_state_projection, root zone, season workspace,
# reports, soil_enrichment), in one place.
LEGACY_ANALYTE_KEYS: dict[str, tuple[str, ...]] = {
    "ec_dsm": ("ec_dsm", "ec_ds_m", "ec", "ece", "ece_ds_m", "salinity_ec", "soil_ec"),
    "ph": ("ph", "pH", "soil_ph"),
    "texture": ("texture", "soil_texture", "textural_class", "texture_class"),
    "organic_matter_pct": ("organic_matter_pct", "om_pct", "organic_matter", "om"),
    "phosphorus_mg_kg": ("phosphorus_mg_kg", "p_ppm", "phosphorus_ppm", "p"),
    "potassium_mg_kg": ("potassium_mg_kg", "k_mg_kg", "k_ppm", "k"),
    "nitrogen_mg_kg": ("nitrogen_mg_kg", "n_ppm"),
}


def _json_object(value) -> dict[str, Any]:
    value = _analyte_value(value)
    return value if isinstance(value, dict) else {}


def usable_analyte_value(analyte: str, value):
    """A texture is a non-empty label; every other analyte a real number. Else None."""
    if analyte == "texture":
        return value.strip() if isinstance(value, str) and value.strip() else None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def legacy_analyte_value(result, analyte: str):
    """The analyte's value in a legacy ``soil_lab_tests.result`` (first usable alias), or None."""
    data = _json_object(result)
    for key in LEGACY_ANALYTE_KEYS.get(analyte, (analyte,)):
        value = usable_analyte_value(analyte, data.get(key))
        if value is not None:
            return value
    return None


def soil_lab_source(evidence_ref: str | None) -> str:
    return (
        SOIL_LAB_LEGACY_SOURCE
        if str(evidence_ref or "").startswith("soil_lab_tests:")
        else SOIL_LAB_CANONICAL_SOURCE
    )


async def soil_analyte_candidates(
    conn, *, field_id: str, analyte: str, tenant_id: str | None = None, limit: int = 20
) -> list:
    """Eligible rows for one analyte, newest collection date first (v156 wins a tie).

    Each row: ``sampled_on`` (with ``sampled_on_source``), ``result`` (``{analyte: value}``
    for v156, the raw legacy object otherwise), ``evidence_ref``
    (``soil_lab_results:<result_id>`` or ``soil_lab_tests:<test_id>``), ``method_code``
    (v156 only), ``legacy_status`` (the legacy row's ``status``, ``approved`` or
    ``published``; None for v156) and ``age_days``. Reads under the caller's tenant RLS;
    ``tenant_id`` adds an explicit filter for callers that hold it.
    """
    return await conn.fetch(
        """SELECT sampled_on, sampled_on_source, result, evidence_ref, method_code,
                  legacy_status,
                  EXTRACT(EPOCH FROM (now() - sampled_on)) / 86400.0 AS age_days
           FROM (
             SELECT COALESCE(s.sampled_on, s.created_at::date) AS sampled_on,
                    CASE WHEN s.sampled_on IS NULL THEN 'sample_created_at'
                         ELSE 'sampled_on' END AS sampled_on_source,
                    jsonb_build_object($2::text, r.value_json) AS result,
                    'soil_lab_results:' || r.result_id::text AS evidence_ref,
                    r.method_code, 1 AS source_priority, r.observed_at AS observed_at,
                    NULL::text AS legacy_status
             FROM lab_samples s JOIN soil_lab_results r
               ON s.tenant_id=r.tenant_id AND s.sample_id=r.sample_id
             WHERE s.field_id=$1 AND s.kind='soil' AND s.status NOT IN ('rejected','cancelled')
               AND r.analyte=$2 AND r.quality_status='approved' AND r.observed_at <= now()
               AND ($4::uuid IS NULL OR s.tenant_id=$4::uuid)
             UNION ALL
             SELECT COALESCE(sampled_on, created_at::date),
                    CASE WHEN sampled_on IS NULL THEN 'legacy_created_at' ELSE 'sampled_on' END,
                    result, 'soil_lab_tests:' || test_id, NULL, 0, updated_at, status
             FROM soil_lab_tests WHERE field_id=$1 AND status IN ('approved','published')
               AND result ?| $3::text[] AND ($4::uuid IS NULL OR tenant_id=$4::uuid)
           ) AS evidence
           WHERE sampled_on <= CURRENT_DATE
           ORDER BY sampled_on DESC, source_priority DESC, observed_at DESC, evidence_ref
           LIMIT $5""",
        field_id,
        analyte,
        list(LEGACY_ANALYTE_KEYS.get(analyte, (analyte,))),
        tenant_id,
        limit,
    )


def _analyte_reading(row, analyte: str, value) -> dict[str, Any]:
    ref = str(row["evidence_ref"])
    source = soil_lab_source(ref)
    row_id = ref.split(":", 1)[1]
    age = row["age_days"]
    return {
        "available": True,
        "analyte": analyte,
        "value": value,
        "source": source,
        "sampled_on": row["sampled_on"],
        "sampled_on_source": row["sampled_on_source"],
        "age_days": float(age) if age is not None else None,
        "result_id": row_id if source == SOIL_LAB_CANONICAL_SOURCE else None,
        "test_id": row_id if source == SOIL_LAB_LEGACY_SOURCE else None,
        "evidence_ref": ref,
        "legacy_status": _row_get(row, "legacy_status")
        if source == SOIL_LAB_LEGACY_SOURCE
        else None,
    }


def _row_get(row, key: str):
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _skip_legacy(row, *, include_legacy: bool, legacy_published_only: bool) -> bool:
    """True when a legacy ``soil_lab_tests`` candidate must not be read: all of them under
    ``include_legacy=False``; under ``legacy_published_only`` every legacy row whose status is
    not ``published`` (a row without a status is skipped: fail closed)."""
    if soil_lab_source(row["evidence_ref"]) != SOIL_LAB_LEGACY_SOURCE:
        return False
    if not include_legacy:
        return True
    return legacy_published_only and _row_get(row, "legacy_status") != "published"


def _candidate_value(row, analyte: str):
    result = _json_object(row["result"])
    if soil_lab_source(row["evidence_ref"]) == SOIL_LAB_LEGACY_SOURCE:
        return legacy_analyte_value(result, analyte)
    return usable_analyte_value(analyte, result.get(analyte))


def _is_ece(row) -> bool:
    """A legacy EC is read as ECe (the frozen table never recorded an extract); a v156 EC is
    an ECe only when measured on a saturated paste."""
    return (
        soil_lab_source(row["evidence_ref"]) == SOIL_LAB_LEGACY_SOURCE
        or row["method_code"] == ECE_EXTRACTION_METHOD
    )


async def soil_ece_evidence(
    conn,
    *,
    field_id: str,
    tenant_id: str | None = None,
    include_legacy: bool = True,
    legacy_published_only: bool = False,
) -> dict[str, Any]:
    """The field's ECe evidence, one rule for every salinity reader.

    ``ece``: the newest approved EC reading when it is an ECe, else None. Samples with no EC
    (pH-only, texture-only, ...) are not EC candidates, so they never hide an older ECe.
    ``newer_other_extract``: the newest approved v156 EC when it is *not* an ECe (1:5, 1:2.5,
    1:1, unspecified); it makes ``ece`` None because it may contradict an older ECe.
    ``prior_ece``: the newest ECe older than that extract. It is not the current ECe, but a
    reader must not drop what it says silently: a critical prior ECe still escalates.
    ``include_legacy=False`` skips the frozen ``soil_lab_tests`` rows (callers that do not
    accept an approved-but-unpublished legacy row) and so drops published legacy rows too;
    ``legacy_published_only=True`` skips only the legacy rows that are not ``published``, so
    a reader that accepts published legacy rows (season readiness) still sees a published
    legacy ECe newer than a v156 extract, as ``field_state`` does."""
    rows = await soil_analyte_candidates(
        conn, field_id=field_id, analyte="ec_dsm", tenant_id=tenant_id
    )
    return ece_evidence_from_candidates(
        rows, include_legacy=include_legacy, legacy_published_only=legacy_published_only
    )


def ece_evidence_from_candidates(
    rows, *, include_legacy: bool = True, legacy_published_only: bool = False
) -> dict[str, Any]:
    """``soil_ece_evidence`` over ``soil_analyte_candidates(analyte='ec_dsm')`` rows."""
    ece = other = prior = None
    for row in rows:
        if _skip_legacy(
            row, include_legacy=include_legacy, legacy_published_only=legacy_published_only
        ):
            continue
        value = _candidate_value(row, "ec_dsm")
        if value is None:
            continue
        if _is_ece(row):
            if other is None:
                ece = _analyte_reading(row, "ec_dsm", value)
            else:
                prior = _analyte_reading(row, "ec_dsm", value)
            break
        if other is None:
            other = {
                **_analyte_reading(row, "ec_dsm", value),
                "extraction_method": row["method_code"] or "unspecified",
                "ece": False,
            }
    return {"ece": ece, "newer_other_extract": other, "prior_ece": prior}


async def latest_approved_soil_analyte(
    conn,
    *,
    field_id: str,
    analyte: str,
    tenant_id: str | None = None,
    accept=None,
    include_legacy: bool = True,
) -> dict[str, Any] | None:
    """The newest usable approved value of one analyte, labelled with its source, or None.

    None means unavailable — never zero. ``accept(value)`` may narrow what counts as usable
    (the TAW table skips texture labels it does not know). ``include_legacy=False`` skips
    the frozen ``soil_lab_tests`` rows, so a legacy row the caller would reject does not
    hide an older approved v156 value.

    ``ec_dsm`` is read as ECe (``soil_ece_evidence``): when the newest approved EC was not
    measured on a saturated paste the ECe is unavailable (None). It does not fall back to an
    older ECe, which the newer reading may contradict."""
    if analyte == "ec_dsm":
        reading = (
            await soil_ece_evidence(
                conn, field_id=field_id, tenant_id=tenant_id, include_legacy=include_legacy
            )
        )["ece"]
        if reading is not None and (accept is None or accept(reading["value"])):
            return reading
        return None
    for row in await soil_analyte_candidates(
        conn, field_id=field_id, analyte=analyte, tenant_id=tenant_id
    ):
        if not include_legacy and soil_lab_source(row["evidence_ref"]) == SOIL_LAB_LEGACY_SOURCE:
            continue
        value = _candidate_value(row, analyte)
        if value is not None and (accept is None or accept(value)):
            return _analyte_reading(row, analyte, value)
    return None


async def latest_approved_soil_analysis(
    conn, *, field_id: str, tenant_id: str | None = None
) -> dict[str, Any] | None:
    """The field's newest approved soil analysis (one sample), labelled with its source.

    v156: ``values`` holds the newest approved value per analyte of that sample and
    ``result_ids`` the rows they came from; ``ec_dsm`` only when it is an ECe (saturated
    paste), any other EC extract is in ``ec_other_extract``. Legacy fallback: ``values`` holds the analytes
    recognised in the free-form result (``LEGACY_ANALYTE_KEYS``) and ``legacy_result`` the
    object as stored, so a reader keeps its own key reading. None when neither exists."""
    head = await conn.fetchrow(
        """SELECT ref_id, sampled_on, sampled_on_source, source_priority, legacy_result,
                  legacy_status FROM (
             SELECT s.sample_id AS ref_id, COALESCE(s.sampled_on, s.created_at::date) AS sampled_on,
                    CASE WHEN s.sampled_on IS NULL THEN 'sample_created_at'
                         ELSE 'sampled_on' END AS sampled_on_source,
                    1 AS source_priority, max(r.observed_at) AS observed_at,
                    NULL::jsonb AS legacy_result, NULL::text AS legacy_status
             FROM lab_samples s JOIN soil_lab_results r
               ON s.tenant_id=r.tenant_id AND s.sample_id=r.sample_id
             WHERE s.field_id=$1 AND s.kind='soil' AND s.status NOT IN ('rejected','cancelled')
               AND r.quality_status='approved' AND r.observed_at <= now()
               AND ($2::uuid IS NULL OR s.tenant_id=$2::uuid)
             GROUP BY s.sample_id, s.sampled_on, s.created_at
             UNION ALL
             SELECT test_id, COALESCE(sampled_on, created_at::date),
                    CASE WHEN sampled_on IS NULL THEN 'legacy_created_at' ELSE 'sampled_on' END,
                    0, updated_at, result, status::text
             FROM soil_lab_tests WHERE field_id=$1 AND status IN ('approved','published')
               AND result <> '{}'::jsonb AND ($2::uuid IS NULL OR tenant_id=$2::uuid)
           ) AS evidence
           WHERE sampled_on <= CURRENT_DATE
           ORDER BY sampled_on DESC, source_priority DESC, observed_at DESC, ref_id
           LIMIT 1""",
        field_id,
        tenant_id,
    )
    if head is None:
        return None
    if head["source_priority"] == 0:
        legacy = _json_object(head["legacy_result"])
        values = {
            analyte: value
            for analyte in LEGACY_ANALYTE_KEYS
            if (value := legacy_analyte_value(legacy, analyte)) is not None
        }
        return {
            "available": True,
            "source": SOIL_LAB_LEGACY_SOURCE,
            "sample_id": None,
            "test_id": head["ref_id"],
            "sampled_on": head["sampled_on"],
            "sampled_on_source": head["sampled_on_source"],
            "values": values,
            "result_ids": {},
            "ec_other_extract": None,
            "legacy_result": legacy,
            "legacy_status": head["legacy_status"],
            "evidence_ref": f"soil_lab_tests:{head['ref_id']}",
        }
    rows = await conn.fetch(
        """SELECT DISTINCT ON (r.analyte) r.analyte, r.result_id, r.value_json, r.method_code
           FROM lab_samples s JOIN soil_lab_results r
             ON s.tenant_id=r.tenant_id AND s.sample_id=r.sample_id
           WHERE s.sample_id=$1 AND r.quality_status='approved' AND r.observed_at <= now()
             AND ($2::uuid IS NULL OR s.tenant_id=$2::uuid)
           ORDER BY r.analyte, r.observed_at DESC, r.received_at DESC, r.result_id DESC""",
        head["ref_id"],
        tenant_id,
    )
    values: dict[str, Any] = {}
    result_ids: dict[str, str] = {}
    ec_other_extract = None
    for row in rows:
        value = usable_analyte_value(row["analyte"], _analyte_value(row["value_json"]))
        if value is None:
            continue
        if row["analyte"] == "ec_dsm" and row["method_code"] != ECE_EXTRACTION_METHOD:
            # Not an ECe: labelled, kept out of ``values`` (and so out of the ECe signal).
            ec_other_extract = {
                "value_dsm": value,
                "extraction_method": row["method_code"] or "unspecified",
                "result_id": str(row["result_id"]),
                "ece": False,
            }
            continue
        values[row["analyte"]] = value
        result_ids[row["analyte"]] = str(row["result_id"])
    return {
        "available": True,
        "source": SOIL_LAB_CANONICAL_SOURCE,
        "sample_id": head["ref_id"],
        "test_id": None,
        "sampled_on": head["sampled_on"],
        "sampled_on_source": head["sampled_on_source"],
        "values": values,
        "result_ids": result_ids,
        "ec_other_extract": ec_other_extract,
        "legacy_result": None,
        "legacy_status": None,
        "evidence_ref": f"lab_samples:{head['ref_id']}",
    }


_LEGACY_SOIL_TEST_COLUMNS = (
    "test_id, field_id, status, lab_name, sampled_on, result, notes_ar, "
    "approved_by, published_at, created_at"
)


async def legacy_soil_lab_test_rows(conn, *, field_id: str, limit: int | None = None) -> list:
    """The frozen legacy ``soil_lab_tests`` rows of a field, newest first (read-only archive).

    New results are recorded through ``/api/v1/lab/*``; this listing only shows history."""
    return await conn.fetch(
        f"SELECT {_LEGACY_SOIL_TEST_COLUMNS} FROM soil_lab_tests "
        "WHERE field_id = $1 ORDER BY created_at DESC LIMIT $2",
        field_id,
        limit,
    )
