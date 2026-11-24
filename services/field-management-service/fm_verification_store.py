"""Owner-side persistence and source checks for the optional scouting bridge.

All writes stay in field-management. Season links and geometry are read from
their owners' existing records. A missing mapping is an explicit refusal.
Network requests happen outside these transactions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from fm_gateway import INSPECTION_REVIEW, OBSERVATION_RECORD, Caller, canonical_role, require
from fm_task_inspection import _load, view
from fm_verification_contracts import (
    AssessmentRequest,
    LinkRequest,
    assessment_record,
    canonical,
    digest,
    wire,
)

from shared.contracts.remote_sensing import EvidenceRefV1
from shared.contracts.remote_sensing.verification_delivery import canonical_completion_payload


def object_value(value):
    return json.loads(value) if isinstance(value, str) else value


async def require_actor(conn, caller: Caller, field_id: str, permission: str = INSPECTION_REVIEW):
    require(caller, permission)
    user = await conn.fetchrow(
        "SELECT role, active FROM users WHERE tenant_id=$1::uuid AND id::text=$2 FOR SHARE",
        caller.tenant_id,
        caller.user_id,
    )
    if not user or not user["active"] or canonical_role(user["role"]) != caller.role:
        raise HTTPException(403, "verification_reviewer_inactive_or_role_changed")
    field = await conn.fetchrow(
        "SELECT farm_id, geometry, geometry_version FROM fields "
        "WHERE tenant_id=$1::uuid AND field_id=$2 FOR SHARE",
        caller.tenant_id,
        field_id,
    )
    if not field or not field["farm_id"]:
        raise HTTPException(404, "verification_field_farm_unavailable")
    # This new opt-in operation requires a current grant, independently of the
    # global migration switch. It neither enables global farm RLS nor writes grants.
    if caller.role != "owner":
        grant = await conn.fetchrow(
            "SELECT is_active FROM farm_access_grants WHERE tenant_id=$1::uuid "
            "AND user_id=$2 AND farm_id=$3",
            caller.tenant_id,
            caller.user_id,
            field["farm_id"],
        )
        if not grant or grant["is_active"] is not True:
            raise HTTPException(403, "verification_farm_grant_required")
    return dict(field)


async def anomaly_task(conn, caller, field_id, task_id, *, lock=False):
    row = await conn.fetchrow(
        "SELECT task_id, anomaly_ref, season_id, geometry_ref, status FROM field_tasks "
        "WHERE tenant_id=$1::uuid AND field_id=$2 AND task_id=$3 "
        "AND anomaly_ref IS NOT NULL AND source_scouting_pin_id IS NULL "
        + ("FOR UPDATE" if lock else "FOR SHARE"),
        caller.tenant_id,
        field_id,
        task_id,
    )
    if not row:
        raise HTTPException(404, "anomaly_scouting_task_not_found")
    if row["status"] not in {"pending", "in_progress", "completed"}:
        raise HTTPException(409, "anomaly_scouting_task_not_eligible")
    return dict(row)


async def resolve_scope(
    conn,
    caller,
    field_id,
    task_id,
    inspection_id,
    season_binding,
    remote,
    *,
    permission=INSPECTION_REVIEW,
):
    field = await require_actor(conn, caller, field_id, permission)
    a = await anomaly_task(conn, caller, field_id, task_id)
    b, _events = await _load(conn, caller, field_id, inspection_id, write=False)
    record = remote.get("anomaly")
    if not isinstance(record, dict) or remote.get("persisted") is not True:
        raise HTTPException(409, "anomaly_owner_context_unavailable")
    if remote.get("snapshot_digest") != digest(record):
        raise HTTPException(409, "anomaly_owner_snapshot_digest_mismatch")
    if (
        str(record.get("tenant_id")) != caller.tenant_id
        or record.get("field_id") != field_id
        or record.get("season_id") != a["season_id"]
        or record.get("anomaly_ref") != a["anomaly_ref"]
        or record.get("task_ref") != f"urn:sahool:task:{task_id}"
    ):
        raise HTTPException(409, "anomaly_owner_scope_mismatch")
    if record.get("status") != "verification_requested":
        raise HTTPException(409, "anomaly_not_waiting_for_this_verification_round")
    payload = record.get("payload") or {}
    if a["geometry_ref"] != payload.get("geometry_ref"):
        raise HTTPException(409, "anomaly_target_reference_changed")
    # Current EO production emits a field signal with geometry_ref=None. A URN
    # alone cannot resolve a subfield polygon: refuse that extension until its
    # geometry owner supplies a versioned resolver. Never substitute the whole field.
    if a["geometry_ref"] is not None:
        raise HTTPException(409, "subfield_geometry_resolver_required")
    geometry = object_value(field["geometry"])
    if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise HTTPException(409, "field_boundary_required")
    pin = await conn.fetchrow(
        "SELECT lat, lng FROM scouting_pins WHERE tenant_id=$1::uuid AND field_id=$2 AND pin_id=$3",
        caller.tenant_id,
        field_id,
        b["pin_id"],
    )
    if pin is None or not await conn.fetchval(
        "SELECT ST_Covers(ST_SetSRID(ST_GeomFromGeoJSON($1),4326), "
        "ST_SetSRID(ST_MakePoint($2,$3),4326))",
        canonical(geometry),
        pin["lng"],
        pin["lat"],
    ):
        raise HTTPException(409, "inspection_site_not_in_current_field_boundary")
    heads = await conn.fetch(
        "SELECT e.event_id,e.action,e.season_id,s.accepted_by,s.accepted_at,s.trust_status "
        "FROM scout_photo_season_link_events e JOIN season_records s "
        "ON s.id=e.season_id AND s.tenant_id=e.tenant_id AND s.field_id=e.field_id "
        "WHERE e.tenant_id=$1::uuid AND e.field_id=$2 AND e.pin_id=$3 "
        "AND NOT EXISTS (SELECT 1 FROM scout_photo_season_link_events n "
        "WHERE n.previous_event_id=e.event_id) LIMIT 2",
        caller.tenant_id,
        field_id,
        b["pin_id"],
    )
    if len(heads) != 1:
        raise HTTPException(409, "inspection_accepted_season_link_required")
    head = heads[0]
    if (
        head["action"] != "link"
        or head["trust_status"] != "accepted"
        or not head["accepted_by"]
        or head["accepted_at"] is None
    ):
        raise HTTPException(409, "inspection_accepted_season_link_required")
    mapping_id = None
    if season_binding == "accepted_record":
        if a["season_id"] != str(head["season_id"]):
            raise HTTPException(409, "inspection_season_mismatch")
    else:
        mappings = await conn.fetch(
            "SELECT l.link_id FROM season_record_links l WHERE l.tenant_id=$1::uuid "
            "AND l.field_id=$2 AND l.canonical_season_id=$3 AND l.season_record_id=$4 "
            "AND l.link_status='active' AND NOT EXISTS "
            "(SELECT 1 FROM season_record_links n WHERE n.supersedes_link_id=l.link_id) LIMIT 2",
            caller.tenant_id,
            field_id,
            a["season_id"],
            head["season_id"],
        )
        if len(mappings) != 1:
            raise HTTPException(409, "canonical_to_accepted_season_mapping_required")
        mapping_id = str(mappings[0]["link_id"])
    scope = wire(
        {
            "tenant_id": caller.tenant_id,
            "farm_id": field["farm_id"],
            "field_id": field_id,
            "anomaly_task_id": task_id,
            "anomaly_ref": a["anomaly_ref"],
            "inspection_task_id": inspection_id,
            "pin_id": b["pin_id"],
            "season_id": a["season_id"],
            "season_binding": season_binding,
            "season_record_id": head["season_id"],
            "season_link_event_id": head["event_id"],
            "canonical_record_link_id": mapping_id,
            "field_geometry_version": field["geometry_version"],
            "field_geometry": geometry,
            "field_geometry_digest": digest(geometry),
            "inspection_site": dict(pin),
            "target": "field_signal",
            "site_is_representative_of_target": "not_inferred",
        }
    )
    context = {"scope": scope, "anomaly_snapshot_digest": remote["snapshot_digest"]}
    return {**context, "context_digest": digest(context), "anomaly": record}


async def link_replay(conn, caller, field_id, task_id, req: LinkRequest):
    await require_actor(conn, caller, field_id)
    row = await conn.fetchrow(
        "SELECT v.link_id,v.revision,v.command_digest,v.created_by,v.field_id,l.anomaly_task_id "
        "FROM scouting_verification_versions v JOIN scouting_verification_links l USING (link_id) "
        "WHERE v.tenant_id=$1::uuid AND v.command_id=$2",
        caller.tenant_id,
        req.command_id,
    )
    if row:
        if (
            row["field_id"] != field_id
            or row["anomaly_task_id"] != task_id
            or row["created_by"] != caller.user_id
            or row["command_digest"].strip() != digest(req.model_dump(mode="json"))
        ):
            raise HTTPException(409, "link_command_reused_with_different_content")
        return {
            "persisted": True,
            "replayed": True,
            "link_id": str(row["link_id"]),
            "revision": row["revision"],
        }
    return None


async def write_link(conn, caller, field_id, task_id, req: LinkRequest, context):
    await conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
        f"verification-link:{caller.tenant_id}:{req.command_id}",
    )
    replay = await link_replay(conn, caller, field_id, task_id, req)
    if replay:
        return replay
    await anomaly_task(conn, caller, field_id, task_id, lock=True)
    if req.expected_context_digest != context["context_digest"]:
        raise HTTPException(409, "verification_context_changed")
    old = await conn.fetchrow(
        "SELECT link_id,revision FROM scouting_verification_links "
        "WHERE tenant_id=$1::uuid AND anomaly_task_id=$2 FOR UPDATE",
        caller.tenant_id,
        task_id,
    )
    revision = old["revision"] if old else 0
    if revision != req.expected_revision:
        raise HTTPException(409, "verification_link_revision_conflict")
    link_id = old["link_id"] if old else uuid4()
    if old and await conn.fetchval(
        "SELECT true FROM scouting_verification_outbox o JOIN scouting_verification_assessments a "
        "ON a.assessment_id=o.assessment_id WHERE a.link_id=$1 "
        "AND o.state IN ('sending','delivery_unknown','delivery_exhausted','delivered',"
        "'delivered_review_required') LIMIT 1",
        link_id,
    ):
        raise HTTPException(409, "reconcile_prior_delivery_before_relinking")
    if old:
        # The revision moves first: v289 blocks an unsent delivery only once its link revision
        # is actually superseded.
        await conn.execute(
            "UPDATE scouting_verification_links SET revision=$2,inspection_task_id=$3 WHERE link_id=$1",
            link_id,
            revision + 1,
            req.inspection_task_id,
        )
        await conn.execute(
            "UPDATE scouting_verification_outbox o SET state='blocked',last_error='link_superseded',"
            "updated_at=clock_timestamp() FROM scouting_verification_assessments a "
            "WHERE o.assessment_id=a.assessment_id AND a.link_id=$1 "
            "AND o.state IN ('pending','refused')",
            link_id,
        )
    else:
        await conn.execute(
            "INSERT INTO scouting_verification_links "
            "(link_id,tenant_id,field_id,anomaly_task_id,inspection_task_id,revision) "
            "VALUES ($1,$2::uuid,$3,$4,$5,1)",
            link_id,
            caller.tenant_id,
            field_id,
            task_id,
            req.inspection_task_id,
        )
    await conn.execute(
        "INSERT INTO scouting_verification_versions "
        "(tenant_id,field_id,link_id,revision,command_id,command_digest,scope_snapshot,context_digest,"
        "anomaly_snapshot,anomaly_snapshot_digest,expected_anomaly_version,created_by,created_role,reason) "
        "VALUES ($1::uuid,$2,$3,$4,$5,$6,$7::jsonb,$8,$9::jsonb,$10,$11,$12,$13,$14)",
        caller.tenant_id,
        field_id,
        link_id,
        revision + 1,
        req.command_id,
        digest(req.model_dump(mode="json")),
        canonical(context["scope"]),
        context["context_digest"],
        canonical(context["anomaly"]),
        context["anomaly_snapshot_digest"],
        context["anomaly"]["aggregate_version"],
        caller.user_id,
        caller.role,
        req.reason,
    )
    return {"persisted": True, "replayed": False, "link_id": str(link_id), "revision": revision + 1}


async def load_link(conn, caller, field_id, link_id, *, lock=False):
    row = await conn.fetchrow(
        "SELECT l.*,v.scope_snapshot,v.context_digest,v.anomaly_snapshot,v.anomaly_snapshot_digest,"
        "v.expected_anomaly_version FROM scouting_verification_links l "
        "JOIN scouting_verification_versions v ON v.link_id=l.link_id AND v.revision=l.revision "
        "WHERE l.tenant_id=$1::uuid AND l.field_id=$2 AND l.link_id=$3 "
        + ("FOR UPDATE OF l" if lock else "FOR SHARE OF l"),
        caller.tenant_id,
        field_id,
        link_id,
    )
    if not row:
        raise HTTPException(404, "verification_link_not_found")
    data = dict(row)
    for name in ("scope_snapshot", "anomaly_snapshot"):
        data[name] = object_value(data[name])
    return data


async def reviewed_inspection(conn, caller, field_id, link, revision, evidence_version):
    task, events = await _load(conn, caller, field_id, link["inspection_task_id"], write=True)
    current = view(task, events, caller)
    last = events[-1] if events else {}
    # Owner decision 1 (2026-11-24): the assessment is written by the inspection's current
    # assignee, after someone else approved the exact evidence version it rests on.
    if (
        task["status"] not in {"pending", "in_progress", "completed"}
        or not current["evidence_approved"]
        or current["revision"] != revision
        or last.get("action") != "approve"
        or task["assigned_to"] != caller.user_id
        or last.get("assignee") != caller.user_id
        or last.get("actor") in (None, caller.user_id)
        or last.get("evidence_version") != evidence_version
    ):
        raise HTTPException(409, "current_approved_inspection_by_its_assignee_required")
    return wire(
        {
            "task_id": link["inspection_task_id"],
            "pin_id": task["pin_id"],
            "handoff": last,
            "evidence": current["approved_evidence"],
        }
    )


async def assessment_replay(conn, caller, field_id, link_id, req):
    await require_actor(conn, caller, field_id, OBSERVATION_RECORD)
    row = await conn.fetchrow(
        "SELECT a.*,o.delivery_id,o.state FROM scouting_verification_assessments a "
        "JOIN scouting_verification_outbox o ON o.assessment_id=a.assessment_id "
        "WHERE a.tenant_id=$1::uuid AND a.command_id=$2",
        caller.tenant_id,
        req.command_id,
    )
    if row:
        if (
            row["field_id"] != field_id
            or row["link_id"] != link_id
            or row["reviewer"] != caller.user_id
            or row["command_digest"].strip() != digest(req.model_dump(mode="json"))
        ):
            raise HTTPException(409, "assessment_command_reused_with_different_content")
        return {
            "persisted": True,
            "replayed": True,
            "assessment_id": str(row["assessment_id"]),
            "delivery_id": str(row["delivery_id"]),
            "delivery_state": row["state"],
        }
    return None


async def write_assessment(conn, caller, field_id, link_id, req: AssessmentRequest, remote):
    await conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
        f"verification-assessment:{caller.tenant_id}:{req.command_id}",
    )
    replay = await assessment_replay(conn, caller, field_id, link_id, req)
    if replay:
        return replay
    link = await load_link(conn, caller, field_id, link_id, lock=True)
    if link["revision"] != req.link_revision:
        raise HTTPException(409, "verification_link_revision_conflict")
    ctx = await resolve_scope(
        conn,
        caller,
        field_id,
        link["anomaly_task_id"],
        link["inspection_task_id"],
        link["scope_snapshot"]["season_binding"],
        remote,
        permission=OBSERVATION_RECORD,
    )
    if ctx["context_digest"] != link["context_digest"].strip():
        raise HTTPException(409, "verification_context_changed")
    inspection = await reviewed_inspection(
        conn, caller, field_id, link, req.expected_inspection_revision, req.evidence_version
    )
    completed = datetime.now(UTC)
    record = assessment_record(
        req,
        scope=ctx["scope"],
        inspection=inspection,
        reviewer=caller.user_id,
        reviewer_role=caller.role,
        completed_at=completed,
    )
    assessment_id, delivery_id = uuid4(), uuid4()
    assessment_text = canonical(record)
    evidence = EvidenceRefV1.model_validate_json(
        canonical(
            {
                "evidence_ref": f"urn:sahool:evidence:scout-{assessment_id.hex}",
                "tenant_id": caller.tenant_id,
                "source_system": "field-management-service",
                "evidence_type": "scouting_verification_assessment",
                "relation_type": "primary",
                "captured_at": wire(completed),
                "content_hash": digest(record),
                "verification_state": "verified",
            }
        )
    )
    body = canonical_completion_payload(
        {
            "expected_version": link["expected_anomaly_version"],
            "task_ref": f"urn:sahool:task:{link['anomaly_task_id']}",
            "verification_result": req.verification_result,
            "evidence_refs": [evidence.evidence_ref],
            "evidence": [evidence.model_dump(mode="json")],
            "reason_codes": req.reason_codes,
            "completed_at": wire(completed),
        }
    )
    await conn.execute(
        "INSERT INTO scouting_verification_assessments "
        "(assessment_id,tenant_id,field_id,link_id,link_revision,command_id,command_digest,"
        "inspection_revision,evidence_version,reviewer,reviewer_role,assessment_text,assessment_digest,completed_at) "
        "VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)",
        assessment_id,
        caller.tenant_id,
        field_id,
        link_id,
        req.link_revision,
        req.command_id,
        digest(req.model_dump(mode="json")),
        req.expected_inspection_revision,
        req.evidence_version,
        caller.user_id,
        caller.role,
        assessment_text,
        digest(record),
        completed,
    )
    await conn.execute(
        "INSERT INTO scouting_verification_outbox "
        "(delivery_id,tenant_id,field_id,assessment_id,idempotency_key,body_text,body_digest) "
        "VALUES ($1,$2::uuid,$3,$4,$5,$6,$7)",
        delivery_id,
        caller.tenant_id,
        field_id,
        assessment_id,
        f"scout-result:{assessment_id.hex}",
        canonical(body),
        digest(body),
    )
    return {
        "persisted": True,
        "replayed": False,
        "assessment_id": str(assessment_id),
        "delivery_id": str(delivery_id),
        "delivery_state": "pending",
        "diagnosis": None,
        "execution_verified": False,
        "training_label_approved": False,
    }


async def load_delivery(conn, caller, field_id, delivery_id, *, lock=False):
    row = await conn.fetchrow(
        "SELECT o.*,a.link_id,a.link_revision,a.reviewer,a.reviewer_role,a.inspection_revision,"
        "a.evidence_version,a.assessment_text FROM scouting_verification_outbox o "
        "JOIN scouting_verification_assessments a ON a.assessment_id=o.assessment_id "
        "WHERE o.tenant_id=$1::uuid AND o.field_id=$2 AND o.delivery_id=$3 "
        + ("FOR UPDATE OF o" if lock else ""),
        caller.tenant_id,
        field_id,
        delivery_id,
    )
    if not row:
        raise HTTPException(404, "verification_delivery_not_found")
    return dict(row)


async def revalidate_delivery(conn, caller, field_id, delivery):
    await require_actor(conn, caller, field_id, OBSERVATION_RECORD)
    if delivery["reviewer"] != caller.user_id or delivery["reviewer_role"] != caller.role:
        raise HTTPException(403, "delivery_requires_the_original_assessor")
    link = await load_link(conn, caller, field_id, delivery["link_id"], lock=True)
    if link["revision"] != delivery["link_revision"]:
        raise HTTPException(409, "delivery_link_superseded")
    # The source checks use the original anomaly snapshot here. The remote owner
    # is checked separately, outside this transaction, before any callback.
    source = {
        "persisted": True,
        "anomaly": link["anomaly_snapshot"],
        "snapshot_digest": link["anomaly_snapshot_digest"].strip(),
    }
    ctx = await resolve_scope(
        conn,
        caller,
        field_id,
        link["anomaly_task_id"],
        link["inspection_task_id"],
        link["scope_snapshot"]["season_binding"],
        source,
        permission=OBSERVATION_RECORD,
    )
    if ctx["context_digest"] != link["context_digest"].strip():
        raise HTTPException(409, "delivery_scope_changed")
    inspection = await reviewed_inspection(
        conn, caller, field_id, link, delivery["inspection_revision"], delivery["evidence_version"]
    )
    if inspection != json.loads(delivery["assessment_text"])["inspection"]:
        raise HTTPException(409, "delivery_inspection_evidence_changed")
    return link
