"""A task's cost trace and expense links (owner: field-management-service).

Rebuilt from the platform routes carrier D #1439 held back (api/routers/tasks.py on
hold/v26-chain-a-held-routes). nginx maps ``/api/v1/field-tasks/...`` here.

* ``POST farm-book/entries/{entry_id}/task`` links an original farm-book expense written before
  v245 gave entries a task to a task (task_expense_links, v276). The v276 guard trigger refuses an
  entry of another farm or field, a non-original entry, or one that names another task; this route
  maps those refusals to 422/409 and additionally refuses an entry whose existing settlements or
  corrections name another farm, field or task. The farm-book entry itself is read, never written.
* ``GET tasks/{task_id}/cost-trace`` shows the task's cost history (v276 trigger), its expenses
  (own task_id or a link, settlements and corrections inherit the original's) and the totals per
  currency. It needs ``analytics:view``: a worker records costs but does not read the trace, the
  same rule as the platform's cost hiding in ``_row_to_task``.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fm_gateway import (
    ACTIVITY_EXECUTE,
    ANALYTICS_VIEW,
    Caller,
    caller_connection,
    caller_dependency,
)
from pydantic import BaseModel

router = APIRouter(prefix="/internal/field-tasks")

# A historical link applies to the original expense and to its settlements and corrections.
LINK_JOIN = """LEFT JOIN task_expense_links link ON link.tenant_id=e.tenant_id
    AND link.entry_id=COALESCE(e.reverses_entry_id, e.settles_entry_id, e.entry_id)"""
EFFECTIVE_TASK = "COALESCE(e.task_id, link.task_id)"

# The v276 guard's refusals, by message.
_LINK_REFUSALS = {
    "original_expense_required": (422, "original_expense_required"),
    "task_farm_mismatch": (422, "task_location_mismatch"),
    "task_field_mismatch": (422, "task_location_mismatch"),
    "entry_already_linked": (409, "entry_already_linked"),
}


class ExpenseTaskIn(BaseModel):
    task_id: UUID


def link_refusal(exc: Exception) -> HTTPException | None:
    """The HTTP answer for a v276 guard refusal (SQLSTATE 23514), else None."""
    if getattr(exc, "sqlstate", None) != "23514":
        return None
    status, code = _LINK_REFUSALS.get(
        str(getattr(exc, "message", "") or exc), (422, "invalid_link")
    )
    return HTTPException(status, code)


def expense_totals(entries) -> dict[str, str]:
    """Net expense per currency: an expense adds, its correction (reverses_entry_id) subtracts."""
    totals: dict[str, Decimal] = {}
    for entry in entries:
        if entry["entry_type"] != "expense":
            continue
        value = Decimal(str(entry["amount"]))
        sign = -1 if entry["reverses_entry_id"] else 1
        totals[entry["currency"]] = totals.get(entry["currency"], Decimal(0)) + sign * value
    return {currency: str(total) for currency, total in totals.items()}


async def _task_scope(conn, caller: Caller, task_id: UUID):
    row = await conn.fetchrow(
        "SELECT t.task_id, t.field_id, f.farm_id FROM field_tasks t "
        "JOIN fields f ON f.tenant_id=t.tenant_id AND f.field_id=t.field_id "
        "WHERE t.tenant_id=$1::uuid AND t.task_id=$2 FOR SHARE OF t",
        caller.tenant_id,
        task_id,
    )
    if row is None:
        raise HTTPException(404, "task_not_found")
    return row


@router.post("/farm-book/entries/{entry_id}/task")
async def link_existing_expense(
    entry_id: str,
    req: ExpenseTaskIn,
    caller: Caller = Depends(caller_dependency(ACTIVITY_EXECUTE)),
):
    try:
        async with caller_connection(caller) as conn:
            entry = await conn.fetchrow(
                """SELECT entry_type, reverses_entry_id, settles_entry_id, field_id, farm_id, task_id
                     FROM farm_ledger_entries WHERE tenant_id=$1::uuid AND entry_id=$2 FOR SHARE""",
                caller.tenant_id,
                entry_id,
            )
            if entry is None:
                raise HTTPException(404, "entry_not_found")
            scope = await _task_scope(conn, caller, req.task_id)
            if entry["task_id"] is not None:
                if entry["task_id"] != req.task_id:
                    raise HTTPException(409, "entry_already_linked")
                return {"entry_id": entry_id, "task_id": req.task_id}
            if await conn.fetchval(
                """SELECT 1 FROM farm_ledger_entries
                    WHERE tenant_id=$1::uuid AND (settles_entry_id=$2 OR reverses_entry_id=$2)
                      AND (farm_id IS DISTINCT FROM $3 OR (field_id IS NOT NULL AND field_id<>$4)
                           OR (task_id IS NOT NULL AND task_id<>$5)) LIMIT 1""",
                caller.tenant_id,
                entry_id,
                scope["farm_id"],
                scope["field_id"],
                req.task_id,
            ):
                raise HTTPException(409, "linked_child_scope_mismatch")
            await conn.execute(
                """INSERT INTO task_expense_links (tenant_id, entry_id, task_id, field_id, linked_by)
                   VALUES ($1::uuid,$2,$3,$4,$5) ON CONFLICT (tenant_id, entry_id) DO NOTHING""",
                caller.tenant_id,
                entry_id,
                req.task_id,
                scope["field_id"],
                caller.user_id,
            )
            linked = await conn.fetchval(
                "SELECT task_id FROM task_expense_links WHERE tenant_id=$1::uuid AND entry_id=$2",
                caller.tenant_id,
                entry_id,
            )
            if linked != req.task_id:
                raise HTTPException(409, "entry_already_linked")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - a guard refusal maps; any other failure is 503
        refusal = link_refusal(exc)
        if refusal is not None:
            raise refusal from exc
        raise HTTPException(503, "field task store unavailable") from exc
    return {"entry_id": entry_id, "task_id": req.task_id}


@router.get("/tasks/{task_id}/cost-trace")
async def task_cost_trace(
    task_id: UUID, caller: Caller = Depends(caller_dependency(ANALYTICS_VIEW))
):
    try:
        async with caller_connection(caller) as conn:
            task = await conn.fetchrow(
                "SELECT t.task_id, t.field_id, t.status, t.actual_cost_usd::text AS actual_cost_usd, "
                "t.estimated_cost_usd::text AS estimated_cost_usd, f.farm_id FROM field_tasks t "
                "JOIN fields f ON f.tenant_id=t.tenant_id AND f.field_id=t.field_id "
                "WHERE t.tenant_id=$1::uuid AND t.task_id=$2",
                caller.tenant_id,
                task_id,
            )
            if task is None:
                raise HTTPException(404, "task_not_found")
            changes = await conn.fetch(
                "SELECT changed_at, changed_by, previous_usd::text AS previous_usd, "
                "actual_usd::text AS actual_usd, previous_status, status FROM task_cost_history "
                "WHERE tenant_id=$1::uuid AND task_id=$2 ORDER BY change_id DESC",
                caller.tenant_id,
                task_id,
            )
            entries = await conn.fetch(
                f"""SELECT e.entry_id, e.entry_type, e.occurred_on, e.category,
                           e.amount::text AS amount, e.currency, e.receipt_document_id,
                           e.reverses_entry_id, e.settles_entry_id,
                           COALESCE(link.linked_by, e.created_by) AS linked_by,
                           COALESCE(link.linked_at, e.created_at) AS linked_at
                      FROM farm_ledger_entries e {LINK_JOIN}
                     WHERE e.tenant_id=$1::uuid AND {EFFECTIVE_TASK}=$2
                     ORDER BY e.occurred_on DESC, e.created_at DESC""",
                caller.tenant_id,
                task_id,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, "field task store unavailable") from exc
    return {
        "task": dict(task),
        "changes": [dict(r) for r in changes],
        "entries": [dict(r) for r in entries],
        "expenses_by_currency": expense_totals(entries),
    }
