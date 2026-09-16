"""Resumable field qualification, separate from data readiness and execution.

The platform owns the journal; domain owners own acquisition and its receipts.
Journal durability is NOT exactly-once provider I/O: handlers must use request_key
and resume saved remote_reference values. No provider calls are hard-coded here.
"""

from __future__ import annotations

import asyncio
import calendar
import copy
import hashlib
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from uuid import UUID

VERSION = "sahool.field_bootstrap.v1"
STEPS = ("soil", "weather_subscription", "weather_history", "imagery_history", "canonical_refresh")
OWNERS = {
    "soil": "soil-service",
    "weather_subscription": "weather-service",
    "weather_history": "weather-service",
    "imagery_history": "raster-service",
    "canonical_refresh": "sahool-platform",
}
HISTORY = {"weather_history", "imagery_history"}
MAX_FAILURES = 5
MAX_POLLS = 2048
STAGE_DEADLINE = timedelta(days=7)
HANDLER_TIMEOUT_SECONDS = 30.0
MAX_RECEIPT_BYTES = 16384
TERMINAL = frozenset({"completed", "blocked", "superseded"})


class BootstrapError(ValueError):
    """Validation errors use stable codes, not provider text."""


class LeaseLost(RuntimeError):
    """A worker must stop; it no longer has authority to checkpoint this job."""


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise BootstrapError("utc_clock_required")
    return value.isoformat()


def _time(value: str) -> datetime:
    if not isinstance(value, str):
        raise BootstrapError("utc_timestamp_required")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise BootstrapError("utc_timestamp_required")
    return result


def _two_years_before(value: date) -> date:
    year = value.year - 2
    return value.replace(year=year, day=min(value.day, calendar.monthrange(year, value.month)[1]))


def _hex(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def new_journal(*, tenant_id: str, field_id: str, geometry: dict, created_at: datetime) -> dict:
    """Freeze 24 calendar months through yesterday, excluding the incomplete day.

    Geometry must first pass the platform's guard. This binds the exact guarded
    JSON; it is not a second geospatial normalization or validation implementation.
    """
    try:
        tenant = str(UUID(tenant_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise BootstrapError("tenant_uuid_required") from exc
    if not isinstance(field_id, str) or not 0 < len(field_id) <= 50:
        raise BootstrapError("invalid_field_id")
    if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise BootstrapError("guarded_geometry_required")
    geometry_digest = _hash(geometry)
    now = _timestamp(created_at)
    end = created_at.date() - timedelta(days=1)
    start = _two_years_before(created_at.date())
    scope = {
        "tenant_id": tenant,
        "field_id": field_id,
        "geometry_digest": geometry_digest,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    stage = {
        "status": "pending",
        "attempts": 0,
        "failures": 0,
        "polls": 0,
        "first_attempt_at": None,
        "next_attempt_at": None,
        "receipt": None,
        "reason": None,
    }
    return {
        "schema_version": VERSION,
        "scope": scope,
        "scope_key": _hash(scope),
        "created_at": now,
        "updated_at": now,
        "next_attempt_at": now,
        "agronomy_ready": False,
        "status": "pending",
        "steps": {name: copy.deepcopy(stage) for name in STEPS},
    }


def request_key(journal: dict, step: str) -> str:
    if step not in STEPS:
        raise BootstrapError("unknown_step")
    return _hash({"scope_key": journal["scope_key"], "step": step, "version": VERSION})


def validate_journal(journal: dict) -> None:
    if not isinstance(journal, dict) or journal.get("schema_version") != VERSION:
        raise BootstrapError("journal_schema")
    scope = journal.get("scope")
    if (
        not isinstance(scope, dict)
        or set(scope) != {"tenant_id", "field_id", "geometry_digest", "start_date", "end_date"}
        or journal.get("scope_key") != _hash(scope)
    ):
        raise BootstrapError("journal_scope_digest")
    try:
        tenant = str(UUID(scope["tenant_id"]))
        start, end = date.fromisoformat(scope["start_date"]), date.fromisoformat(scope["end_date"])
        created = _time(journal["created_at"])
        _time(journal["updated_at"])
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise BootstrapError("journal_scope_invalid") from exc
    if (
        tenant != scope["tenant_id"]
        or not isinstance(scope["field_id"], str)
        or not 0 < len(scope["field_id"]) <= 50
        or not _hex(scope["geometry_digest"])
    ):
        raise BootstrapError("journal_scope_invalid")
    if start != _two_years_before(created.date()) or end != created.date() - timedelta(days=1):
        raise BootstrapError("journal_window_invalid")
    if (
        journal.get("status") not in TERMINAL | {"pending", "running"}
        or type(journal.get("agronomy_ready")) is not bool
    ):
        raise BootstrapError("journal_status_invalid")
    if journal.get("next_attempt_at") is not None:
        _time(journal["next_attempt_at"])
    if not isinstance(journal.get("steps"), dict) or set(journal["steps"]) != set(STEPS):
        raise BootstrapError("journal_steps_invalid")
    for name, state in journal["steps"].items():
        if (
            not isinstance(state, dict)
            or type(state.get("attempts")) is not int
            or not 0 <= state["attempts"] <= MAX_POLLS + MAX_FAILURES + 1
            or type(state.get("failures")) is not int
            or not 0 <= state["failures"] <= MAX_FAILURES
            or type(state.get("polls")) is not int
            or not 0 <= state["polls"] <= MAX_POLLS
            or state.get("status") not in {"pending", "running", "completed", "blocked", "partial"}
        ):
            raise BootstrapError("journal_step_invalid")
        for key in ("first_attempt_at", "next_attempt_at"):
            if state.get(key) is not None:
                _time(state[key])
        if state.get("receipt") is not None:
            validate_receipt(state["receipt"], journal, name)
        if (
            state["status"] == "completed"
            and (state.get("receipt") or {}).get("status") != "completed"
        ):
            raise BootstrapError("journal_completion_without_receipt")
    if journal["status"] == "completed" and any(
        journal["steps"][s]["status"] != "completed" for s in STEPS
    ):
        raise BootstrapError("journal_completion_without_steps")
    if journal["agronomy_ready"] and (
        journal["status"] != "completed"
        or (journal["steps"]["canonical_refresh"].get("receipt") or {}).get("agronomy_ready")
        is not True
    ):
        raise BootstrapError("journal_readiness_not_owner_verified")


def validate_receipt(receipt: dict, journal: dict, step: str) -> dict:
    allowed = {
        "step",
        "scope_key",
        "request_key",
        "source_authority",
        "status",
        "evidence_id",
        "remote_reference",
        "coverage",
        "evidence_class",
        "agronomy_ready",
        "state_digest",
    }
    if not isinstance(receipt, dict) or set(receipt) - allowed:
        raise BootstrapError("unexpected_receipt_shape")
    try:
        encoded = json.dumps(receipt, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        raise BootstrapError("receipt_not_json") from exc
    if len(encoded) > MAX_RECEIPT_BYTES:
        raise BootstrapError("receipt_too_large")
    expected = {
        "step": step,
        "scope_key": journal["scope_key"],
        "request_key": request_key(journal, step),
        "source_authority": OWNERS[step],
    }
    if any(receipt.get(k) != v for k, v in expected.items()):
        raise BootstrapError("receipt_scope_or_owner_mismatch")
    status = receipt.get("status")
    if status not in {"completed", "pending", "partial"}:
        raise BootstrapError("receipt_status_invalid")
    reference = receipt.get("remote_reference" if status == "pending" else "evidence_id")
    if not isinstance(reference, str) or not 0 < len(reference) <= 200:
        raise BootstrapError(
            "pending_remote_reference_required"
            if status == "pending"
            else "evidence_reference_required"
        )
    if "remote_reference" in receipt and (
        not isinstance(receipt["remote_reference"], str)
        or not 0 < len(receipt["remote_reference"]) <= 200
    ):
        raise BootstrapError("invalid_remote_reference")
    if step in HISTORY and status == "completed":
        coverage = receipt.get("coverage")
        if (
            not isinstance(coverage, dict)
            or set(coverage) != {"start_date", "end_date", "complete", "gaps", "sample_count"}
            or coverage.get("start_date") != journal["scope"]["start_date"]
            or coverage.get("end_date") != journal["scope"]["end_date"]
            or coverage.get("complete") is not True
            or coverage.get("gaps") != []
            or type(coverage.get("sample_count")) is not int
            or coverage["sample_count"] <= 0
        ):
            raise BootstrapError("history_completion_not_proven")
    if (
        step == "soil"
        and status == "completed"
        and receipt.get("evidence_class") not in {"modelled", "measured"}
    ):
        raise BootstrapError("soil_evidence_class_required")
    if step == "canonical_refresh" and status == "completed":
        if type(receipt.get("agronomy_ready")) is not bool or not _hex(receipt.get("state_digest")):
            raise BootstrapError("canonical_completion_not_proven")
    return copy.deepcopy(receipt)


class JournalStore(Protocol):
    async def checkpoint(self, job_id: int, token: str, journal: dict) -> None:
        """CAS by job, tenant and unexpired lease token, then COMMIT."""

    async def finish(self, job_id: int, token: str, journal: dict) -> None:
        """CAS, persist journal, release the lease, then COMMIT."""


Handler = Callable[[dict, dict | None], Awaitable[dict]]


@dataclass
class ClaimedJob:
    job_id: int
    token: str
    journal: dict


async def advance(
    job: ClaimedJob,
    *,
    store: JournalStore,
    handlers: dict[str, Handler],
    load_geometry_digest: Callable[[], Awaitable[str]],
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    timeout: float = HANDLER_TIMEOUT_SECONDS,
) -> dict:
    """Run every currently due stage once, checkpointing intent BEFORE provider I/O.

    Provider errors/uncertain interrupted calls consume a bounded failure budget;
    valid pending polls do NOT. Polling has its own seven-day/2048-poll bound. A
    scheduler later retries due work; there is no sleeping retry loop in a worker.
    """
    if (
        type(timeout) not in (int, float)
        or not math.isfinite(timeout)
        or not 0 < timeout <= HANDLER_TIMEOUT_SECONDS
    ):
        raise BootstrapError("handler_timeout_out_of_bounds")
    journal = copy.deepcopy(job.journal)
    validate_journal(journal)
    if journal["status"] in TERMINAL:
        await store.finish(job.job_id, job.token, journal)
        return journal

    async def superseded() -> bool:
        if await load_geometry_digest() == journal["scope"]["geometry_digest"]:
            return False
        journal.update(
            status="superseded",
            agronomy_ready=False,
            next_attempt_at=None,
            updated_at=_timestamp(clock()),
        )
        await store.finish(job.job_id, job.token, journal)
        return True

    for step in STEPS:
        if await superseded():
            return journal
        stage = journal["steps"][step]
        if stage["status"] in {"completed", "blocked"}:
            continue
        if step == "canonical_refresh" and any(
            journal["steps"][s]["status"] != "completed" for s in STEPS[:-1]
        ):
            blocked = any(journal["steps"][s]["status"] == "blocked" for s in STEPS[:-1])
            stage.update(
                status="blocked" if blocked else "pending",
                reason="source_steps_incomplete",
                next_attempt_at=None,
            )
            continue
        now = clock()
        _timestamp(now)
        if stage.get("next_attempt_at") and _time(stage["next_attempt_at"]) > now:
            continue
        if stage["status"] == "running":
            # Previous worker died after checkpointing intent. Idempotency is
            # essential: receipt-less does not prove that the owner did no work.
            stage["failures"] = min(MAX_FAILURES, stage["failures"] + 1)
        expired = (
            stage.get("first_attempt_at") is not None
            and now - _time(stage["first_attempt_at"]) >= STAGE_DEADLINE
        )
        if stage["failures"] >= MAX_FAILURES or stage["polls"] >= MAX_POLLS or expired:
            reason = (
                "stage_deadline_reached"
                if expired
                else "retry_limit_reached"
                if stage["failures"] >= MAX_FAILURES
                else "poll_limit_reached"
            )
            stage.update(status="blocked", reason=reason, next_attempt_at=None)
            await store.checkpoint(job.job_id, job.token, journal)
            continue
        handler = handlers.get(step)
        if handler is None:
            stage.update(
                status="pending",
                reason="owner_adapter_not_configured",
                next_attempt_at=_timestamp(now + timedelta(minutes=5)),
            )
            await store.checkpoint(job.job_id, job.token, journal)
            continue
        stage.update(
            status="running",
            attempts=stage["attempts"] + 1,
            reason=None,
            next_attempt_at=None,
            first_attempt_at=stage["first_attempt_at"] or _timestamp(now),
        )
        journal["updated_at"] = _timestamp(now)
        await store.checkpoint(job.job_id, job.token, journal)
        request = {
            **journal["scope"],
            "scope_key": journal["scope_key"],
            "step": step,
            "request_key": request_key(journal, step),
        }
        try:
            receipt = await asyncio.wait_for(
                handler(request, copy.deepcopy(stage["receipt"])), timeout
            )
        except LeaseLost:
            raise
        except Exception:
            receipt, reason = None, "owner_call_failed"
        else:
            try:
                receipt = validate_receipt(receipt, journal, step)
            except BootstrapError as exc:
                receipt, reason = None, str(exc)
        # A field can be edited while provider I/O is in flight. Never record its
        # old-geometry answer as qualification for the new field revision.
        if await superseded():
            return journal
        if receipt is None:
            stage["failures"] += 1
            stage.update(
                reason=reason, status="blocked" if stage["failures"] >= MAX_FAILURES else "pending"
            )
        else:
            stage["receipt"] = receipt
            stage["status"] = receipt["status"]
            stage["reason"] = None if receipt["status"] == "completed" else "owner_not_complete"
            if receipt["status"] != "completed":
                stage["polls"] += 1
        if stage["status"] in {"pending", "partial"}:
            seconds = 300 if receipt is not None else min(21600, 60 * 2 ** (stage["failures"] - 1))
            stage["next_attempt_at"] = _timestamp(clock() + timedelta(seconds=seconds))
        await store.checkpoint(job.job_id, job.token, journal)

    if await superseded():
        return journal
    done = all(journal["steps"][s]["status"] == "completed" for s in STEPS)
    unfinished_sources = [
        s for s in STEPS[:-1] if journal["steps"][s]["status"] not in {"completed", "blocked"}
    ]
    blocked = any(journal["steps"][s]["status"] == "blocked" for s in STEPS)
    journal["status"] = (
        "completed" if done else "blocked" if blocked and not unfinished_sources else "pending"
    )
    final_receipt = journal["steps"]["canonical_refresh"]["receipt"] or {}
    journal["agronomy_ready"] = bool(done and final_receipt.get("agronomy_ready") is True)
    now = clock()
    journal["updated_at"] = _timestamp(now)
    due = [
        stage.get("next_attempt_at") or _timestamp(now)
        for name, stage in journal["steps"].items()
        if stage["status"] not in {"completed", "blocked"}
        and not (name == "canonical_refresh" and unfinished_sources)
    ]
    journal["next_attempt_at"] = (
        min(due, key=_time) if due and journal["status"] == "pending" else None
    )
    await store.finish(job.job_id, job.token, journal)
    return journal
