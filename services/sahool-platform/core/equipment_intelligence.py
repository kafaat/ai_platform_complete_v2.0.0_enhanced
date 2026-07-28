"""Pure equipment fleet intelligence; no telemetry or physical-device claims.

Fail-closed on absent maintenance policy. An asset is evaluated for service only when
every input the evaluation depends on is actually present:

  service_interval_hours missing -> not_evaluated / maintenance_policy_missing
  last_service_hours     missing -> not_evaluated / service_meter_baseline_missing
  operating_hours        missing -> not_evaluated / current_meter_reading_missing

No absent input may ever produce ``due``, a positive ``overdue_hours``, an assumed
interval, or an assumed last-service meter. A real zero is a real reading and is
evaluated normally -- only absence is absence.

``next_service_date`` is an independent, self-sufficient signal: a scheduled date that
has arrived means the asset is due regardless of meter readings, because that claim
rests on recorded data rather than on an assumption.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

SCHEMA_VERSION = "equipment_intelligence.v2"

STATUS_DUE = "due"
STATUS_NOT_DUE = "not_due"
STATUS_NOT_EVALUATED = "not_evaluated"

BASIS_NEXT_SERVICE_DATE = "next_service_date"
BASIS_SERVICE_METER = "service_meter"

CONSTRAINT_POLICY_MISSING = "maintenance_policy_missing"
CONSTRAINT_BASELINE_MISSING = "service_meter_baseline_missing"
CONSTRAINT_CURRENT_METER_MISSING = "current_meter_reading_missing"
CONSTRAINT_INVALID_NEXT_SERVICE_DATE = "invalid_next_service_date"
CONSTRAINT_METER_NOT_EVALUABLE = "service_meter_not_evaluable"
CONSTRAINT_ALL_ASSETS_NOT_EVALUATED = "all_assets_not_evaluated"

# Readiness vocabulary. Each state means one thing and nothing else:
#   unknown            no evidence sufficient to judge maintenance state
#   attention_required at least one asset is due or overdue
#   degraded           evidenced operational problem (assets unavailable), nothing due
#   ready              every evaluable asset is fine and nothing is due
READINESS_UNKNOWN = "unknown"
READINESS_ATTENTION = "attention_required"
READINESS_DEGRADED = "degraded"
READINESS_READY = "ready"

_UNAVAILABLE_STATUSES = {"broken", "maintenance", "retired", "unavailable"}


@dataclass(frozen=True)
class EquipmentServiceAssessment:
    """Per-asset service verdict.

    ``basis`` names the evidence the verdict rests on, so a ``not_due`` reached from a
    future schedule is never mistaken for one corroborated by the meter.
    ``overdue_hours`` stays None unless genuinely computed.
    """

    asset_id: str
    status: str
    basis: str | None
    overdue_hours: float | None
    constraints: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EquipmentIntelligenceState:
    schema_version: str
    total_assets: int
    service_due: int
    service_not_due: int
    service_not_evaluated: int
    assessment_coverage: float
    unavailable: int
    total_operating_hours: float
    utilization_known_assets: int
    readiness: str
    due_asset_ids: list[str]
    not_evaluated_asset_ids: list[str]
    assessments: list[dict[str, Any]]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _reading(value: Any) -> float | None:
    """Return a finite non-negative reading, or None when absent/unusable.

    ``False``/``True`` are rejected: a boolean is never a meter reading.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number >= 0 else None


def _assess(asset: dict[str, Any], *, aid: str, as_of: date) -> EquipmentServiceAssessment:
    """Gather every independent line of evidence before answering.

    The date path and the meter path are separate sources. A schedule that has arrived
    settles the question; a schedule still in the future settles only that *the date path*
    is not yet due, so the meter is still consulted. Ending the assessment on first sight
    of a date would hide a meter-proven overdue.
    """
    constraints: list[str] = []
    date_not_due = False

    raw_due = asset.get("next_service_date")
    if raw_due:
        try:
            if datetime.fromisoformat(str(raw_due)).date() <= as_of:
                # Recorded schedule that has arrived — a fact, not an assumption.
                return EquipmentServiceAssessment(
                    aid, STATUS_DUE, BASIS_NEXT_SERVICE_DATE, None, []
                )
            date_not_due = True
        except ValueError:
            constraints.append(CONSTRAINT_INVALID_NEXT_SERVICE_DATE)

    current = _reading(asset.get("operating_hours"))
    interval = _reading(asset.get("service_interval_hours"))
    baseline = _reading(asset.get("last_service_hours"))

    if current is None:
        constraints.append(CONSTRAINT_CURRENT_METER_MISSING)
    if interval is None:
        constraints.append(CONSTRAINT_POLICY_MISSING)
    if baseline is None:
        constraints.append(CONSTRAINT_BASELINE_MISSING)

    if current is None or interval is None or baseline is None:
        # Never guess an interval or a baseline.
        if date_not_due:
            # The recorded schedule is real evidence and stands on its own; the
            # constraints say plainly that the meter could not corroborate it.
            constraints.append(CONSTRAINT_METER_NOT_EVALUABLE)
            return EquipmentServiceAssessment(
                aid, STATUS_NOT_DUE, BASIS_NEXT_SERVICE_DATE, None, constraints
            )
        return EquipmentServiceAssessment(aid, STATUS_NOT_EVALUATED, None, None, constraints)

    elapsed = current - baseline
    if elapsed >= interval:
        return EquipmentServiceAssessment(
            aid, STATUS_DUE, BASIS_SERVICE_METER, round(elapsed - interval, 2), constraints
        )
    return EquipmentServiceAssessment(aid, STATUS_NOT_DUE, BASIS_SERVICE_METER, None, constraints)


def summarize_equipment(
    *,
    assets: list[dict[str, Any]],
    as_of: date | None = None,
) -> EquipmentIntelligenceState:
    """Summarise fleet readiness without inventing maintenance policy.

    ``readiness`` reports ``degraded`` when anything is unavailable or due, and
    ``unknown`` when there is nothing to assess or nothing could be assessed — an
    un-evaluated fleet is never reported as ``ready``.
    """
    as_of = as_of or date.today()
    assessments: list[EquipmentServiceAssessment] = []
    limitations: list[str] = []
    unavailable = 0
    hours = 0.0
    known = 0

    for index, asset in enumerate(assets):
        aid = str(asset.get("id") or asset.get("equipment_id") or f"asset-{index}")
        if str(asset.get("status") or "unknown") in _UNAVAILABLE_STATUSES:
            unavailable += 1
        current = _reading(asset.get("operating_hours"))
        if current is None:
            limitations.append(f"{CONSTRAINT_CURRENT_METER_MISSING}:{aid}")
        else:
            hours += current
            known += 1
        assessment = _assess(asset, aid=aid, as_of=as_of)
        assessments.append(assessment)
        for constraint in assessment.constraints:
            limitations.append(f"{constraint}:{aid}")

    due = [a.asset_id for a in assessments if a.status == STATUS_DUE]
    not_due = [a for a in assessments if a.status == STATUS_NOT_DUE]
    not_evaluated = [a.asset_id for a in assessments if a.status == STATUS_NOT_EVALUATED]

    evaluated = len(assets) - len(not_evaluated)
    coverage = round(evaluated / len(assets), 4) if assets else 0.0

    # Precedence: a due asset is actionable and outranks a degradation signal. Absence of
    # evidence is never dressed up as either — it stays unknown, with the shortfall
    # recorded in limitations rather than folded into the verdict.
    if not assets:
        readiness = READINESS_UNKNOWN
        limitations.append("no_equipment_assets")
    elif due:
        readiness = READINESS_ATTENTION
    elif evaluated == 0:
        readiness = READINESS_UNKNOWN
        limitations.append(CONSTRAINT_ALL_ASSETS_NOT_EVALUATED)
    elif unavailable:
        readiness = READINESS_DEGRADED
    else:
        readiness = READINESS_READY

    return EquipmentIntelligenceState(
        schema_version=SCHEMA_VERSION,
        total_assets=len(assets),
        service_due=len(due),
        service_not_due=len(not_due),
        service_not_evaluated=len(not_evaluated),
        assessment_coverage=coverage,
        unavailable=unavailable,
        total_operating_hours=round(hours, 2),
        utilization_known_assets=known,
        readiness=readiness,
        due_asset_ids=due,
        not_evaluated_asset_ids=not_evaluated,
        assessments=[a.to_dict() for a in assessments],
        limitations=list(dict.fromkeys(limitations)),
    )
