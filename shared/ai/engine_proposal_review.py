"""Stored owner-engine proposals for the advisor chat — review only, never executed.

F8 (owner decision): the advisor may SHOW a proposal that an owning engine already
produced and stored for this field, labelled as awaiting specialist review. This module is
the shared contract (pure, no I/O): the platform projects its stored rows through it and
the advisor runtime re-checks what it receives against it. Nothing here runs an engine,
computes a recommendation, lets a model choose or alter an amount, approves or writes.
Every amount is copied from the stored owner record; nothing here is agronomic logic.
The SQL read lives with the table owner (``api/routers/internal_service.py``).

Sources found in the tree (2026-11-22) and how each is treated:

* ``hourly_irrigation_mpc_schedules`` — written by the irrigation engine
  (``api/irrigation_runtime_orchestrator.py::_persist_schedule``), recommendation-only and
  ``execution_allowed = FALSE`` by table CHECK. Projected here.
* fertiliser / 4R (``api/nutrient_4r.py``, ``api/recommendations_hub.py``) — computed per
  request and never stored, so there is no stored proposal to show
  (``owner_engine_persists_no_proposals``). Computing one here is forbidden.
* ``vri_prescriptions`` / ``prescription_maps`` have no production writer; ``prescriptions``
  is hand-drawn by a user, not engine output. Not read.

Feature flag ``SAHOOL_ADVISOR_ENGINE_PROPOSALS`` — OFF by default; read at call time.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared.ai.recommendation_runtime.flags import flag

SCHEMA = "sahool.engine_proposal_review.v1"
FLAG_ENV = "SAHOOL_ADVISOR_ENGINE_PROPOSALS"
MAX_PROPOSALS = 3
_IRRIGATION_SOURCE = "irrigation.hourly_mpc_schedule"
_IRRIGATION_STORE = "hourly_irrigation_mpc_schedules"
_OWNING_SERVICE = "sahool-platform"
_IRRIGATION_ENGINE = "api.irrigation_runtime_orchestrator/api.hourly_energy_aware_irrigation_mpc"
_ELIGIBLE_OWNER_STATUS = frozenset({"verified", "degraded"})
# Amounts and units are copied from the stored record; the keys are the owner's column names.
_AMOUNT_UNITS = {
    "scheduled_irrigation_mm": "mm",
    "scheduled_volume_m3": "m3",
    "required_refill_mm": "mm",
}
_ACTION_UNITS = {
    "hour": "ISO-8601 UTC",
    "irrigation_depth_mm": "mm",
    "irrigation_volume_m3": "m3",
    "runtime_minutes": "min",
}
_SNAPSHOT_UNITS = {"initial_depletion_mm": "mm", "taw_mm": "mm", "raw_mm": "mm"}
_PRESENTATION_AR = "مقترح ري محفوظ من محرّك الري المالك؛ بانتظار مراجعة مختص، ولم يُعتمد ولم يُنفّذ."


def flag_enabled() -> bool:
    return flag("ADVISOR_ENGINE_PROPOSALS", False)


def review_envelope(
    *,
    tenant_id: str,
    field_id: str,
    enabled: bool,
    proposals: list[dict] | None = None,
    reason_codes: list[str] | None = None,
    sources_checked: list[dict] | None = None,
) -> dict:
    proposals = list(proposals or [])
    return {
        "schema_version": SCHEMA,
        "tenant_id": tenant_id,
        "field_id": field_id,
        "feature_flag": FLAG_ENV,
        "enabled": enabled,
        "read_only": True,
        "computed_in_request": False,
        "model_may_alter_amounts": False,
        "requires_human_review": True,
        "proposals": proposals,
        "reason_codes": sorted(set(reason_codes or [])),
        "sources_checked": list(sources_checked or []),
    }


def disabled_envelope(*, tenant_id: str, field_id: str) -> dict:
    return review_envelope(
        tenant_id=tenant_id, field_id=field_id, enabled=False, reason_codes=["feature_flag_off"]
    )


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _aware(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _payload(value: Any) -> dict | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return value if isinstance(value, dict) else None


def project_irrigation_schedule(
    row: Any, *, tenant_id: str, field_id: str, now: datetime
) -> tuple[dict | None, str | None]:
    """One stored irrigation schedule → (proposal, None) or (None, reason_code).

    Pure: no I/O. The proposal carries the stored amounts verbatim; a record missing any
    provenance the review needs is withheld with a reason, never completed by guessing.
    """
    if str(row["tenant_id"]) != tenant_id or row["field_id"] != field_id:
        return None, "owner_record_scope_mismatch"
    if row["recommendation_only"] is not True or row["execution_allowed"] is not False:
        return None, "owner_record_not_recommendation_only"
    if row["status"] not in _ELIGIBLE_OWNER_STATUS:
        return None, "owner_status_blocked"
    payload = _payload(row["payload"])
    if (
        payload is None
        or payload.get("schedule_digest") != row["schedule_digest"]
        or str(payload.get("tenant_id")) != tenant_id
        or payload.get("field_id") != field_id
        or payload.get("recommendation_only") is not True
        or payload.get("execution_allowed") is not False
    ):
        return None, "owner_record_integrity_mismatch"
    limitations = payload.get("limitations")
    source_digests = payload.get("source_digests")
    if not isinstance(limitations, list) or not isinstance(source_digests, dict):
        return None, "owner_record_provenance_incomplete"
    if not isinstance(row["solver_version"], str) or not row["solver_version"]:
        return None, "owner_record_method_version_missing"
    created_at = _aware(row["created_at"])
    valid_from = _aware(row["horizon_start"])
    hours = row["horizon_hours"]
    if created_at is None or valid_from is None or type(hours) is not int or hours <= 0:
        return None, "owner_record_validity_missing"
    valid_until = valid_from + timedelta(hours=hours)
    if now >= valid_until:
        return None, "owner_record_expired"
    amounts = {key: _finite(row[key]) for key in _AMOUNT_UNITS}
    snapshot = {key: _finite(payload.get(key)) for key in _SNAPSHOT_UNITS}
    if any(value is None for value in (*amounts.values(), *snapshot.values())):
        return None, "owner_record_amounts_incomplete"
    actions = []
    for action in payload.get("actions") or []:
        if not isinstance(action, dict):
            return None, "owner_record_amounts_incomplete"
        copied = {"hour": action.get("hour")}
        copied.update({k: _finite(action.get(k)) for k in _ACTION_UNITS if k != "hour"})
        if not isinstance(copied["hour"], str) or None in copied.values():
            return None, "owner_record_amounts_incomplete"
        actions.append(copied)
    return {
        "proposal_id": f"{_IRRIGATION_SOURCE}:{row['schedule_id']}",
        "proposal_kind": "irrigation",
        "status": "awaiting_specialist_review",
        "requires_human_review": True,
        "approved": False,
        "executable": False,
        "execution_allowed": False,
        "recommendation_only": True,
        "computed_in_request": False,
        "tenant_id": tenant_id,
        "field_id": field_id,
        "owning_service": _OWNING_SERVICE,
        "owning_engine": _IRRIGATION_ENGINE,
        "source_record": {
            "store": _IRRIGATION_STORE,
            "record_id": row["schedule_id"],
            "record_digest": row["schedule_digest"],
        },
        "method": {
            "name": "hourly_energy_aware_lexicographic_mpc",
            "version": row["solver_version"],
            "schema_version": payload.get("schema_version"),
        },
        "owner_status": row["status"],
        "owner_decision": payload.get("decision"),
        "amounts": amounts,
        "actions": actions,
        "units": {**_AMOUNT_UNITS, **{f"actions[].{k}": u for k, u in _ACTION_UNITS.items()}},
        "input_snapshot": {
            "season_id": row["season_id"],
            **snapshot,
            "units": dict(_SNAPSHOT_UNITS),
            "source_digests": dict(source_digests),
        },
        "timestamps": {"created_at": _iso(created_at), "read_at": _iso(now)},
        "validity": {
            "valid_from": _iso(valid_from),
            "valid_until": _iso(valid_until),
            "horizon_hours": hours,
            "state": "current",
            "basis": "owner_schedule_horizon",
        },
        "limitations": [str(item) for item in limitations],
        "presentation_ar": _PRESENTATION_AR,
    }, None


def build_review(rows: list[Any], *, tenant_id: str, field_id: str, now: datetime) -> dict:
    """Envelope for the stored rows the owner read for one field (pure)."""
    tenant_id = str(UUID(str(tenant_id)))
    proposals: list[dict] = []
    reasons: list[str] = []
    for row in rows:
        proposal, reason = project_irrigation_schedule(
            row, tenant_id=tenant_id, field_id=field_id, now=now
        )
        if proposal is None:
            reasons.append(reason)
        elif len(proposals) < MAX_PROPOSALS:
            proposals.append(proposal)
    if not rows:
        reasons.append("no_stored_owner_proposal")
    elif not proposals:
        reasons.append("no_eligible_stored_owner_proposal")
    reasons.append("fertilization_owner_engine_persists_no_proposals")
    return review_envelope(
        tenant_id=tenant_id,
        field_id=field_id,
        enabled=True,
        proposals=proposals,
        reason_codes=reasons,
        sources_checked=[
            {
                "source": _IRRIGATION_SOURCE,
                "proposal_kind": "irrigation",
                "owning_service": _OWNING_SERVICE,
                "store": _IRRIGATION_STORE,
                "rows_examined": len(rows),
                "eligible": len(proposals),
            },
            {
                "source": "fertilization.nutrient_4r",
                "proposal_kind": "fertilization",
                "owning_service": _OWNING_SERVICE,
                "store": None,
                "rows_examined": 0,
                "eligible": 0,
                "reason_code": "owner_engine_persists_no_proposals",
            },
        ],
    )
