"""core/governance_farm_context.py — server-side farm facts for the governance gate (W1-12).

guardrails-engine asks for farm economics and seasonal water before it rules on a spending
action (``services/guardrails-engine/contracts.py``). Those facts are recorded in the farm
operations ledger, the revenue records, the water records and ``water_ledger``, and nothing
read them (findings x-3, airuntime-3). This module reads them, for one tenant, and returns a
``farm_context`` whose every value carries its source.

Rules (fail closed: an absent key makes the gate return ``evidence_unavailable``, never a
guess):

- Amounts are never converted between currencies and never summed across them. The
  guardrails keys are in USD, so ``annual_*_usd`` / ``season_*_usd`` are emitted only when every
  amount in their scope is recorded in USD. Other currencies stay in per-currency blocks.
- No recorded row is not zero: costs or revenue with no rows are unavailable, not ``0``.
- Costs with unpriced completed work are incomplete, so the cost total is not emitted (a
  missing cost would read as a lower cost).
- ``cash_reserve_usd`` has no server source today and is always unavailable.
- Water: a day's metered volume (``farm_water_records``) wins over the ``water_ledger``
  irrigation depth for the same day (no double count); a day with an unmeasured record and no
  ledger depth makes the season total incomplete, so it is not emitted.

The caller passes a connection already scoped to the tenant (``tenant_connection``); every
query also binds ``tenant_id`` explicitly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from core.farm_operations_ledger import ACTUAL_OPERATION_SQL, normalize_currency

SCHEMA = "sahool.governance_farm_context/v1"
ANNUAL_WINDOW_DAYS = 365
NO_SERVER_SOURCE = "no_server_source"

#: ``fields.water_source`` vocabulary (well/canal/river/rainfed/tank/mixed) to the classes
#: guardrails accepts. Anything else (rainfed, tank, free text) is not mapped.
WATER_SOURCE_CLASS = {
    "well": "groundwater",
    "groundwater": "groundwater",
    "borehole": "groundwater",
    "canal": "surface",
    "river": "surface",
    "surface": "surface",
    "mixed": "mixed",
}

_FIELD_SQL = """SELECT field_id, farm_id, area_ha, water_source
                FROM fields WHERE tenant_id = $1::uuid AND field_id = $2"""

_SEASON_SQL = """
    SELECT 'seasons' AS source, field_id,
           COALESCE(sowing_date, plowing_date, land_leveling_date) AS start_date,
           season_end AS end_date
      FROM seasons WHERE tenant_id = $1::uuid AND season_id = $2
    UNION ALL
    SELECT 'farm_season_projects', NULL, start_date, end_date
      FROM farm_season_projects WHERE tenant_id = $1::uuid AND season_id = $2
    LIMIT 1"""

_SEASON_COSTS_SQL = f"""
    SELECT upper(trim(currency)) AS currency,
           SUM(cost_amount)::float AS amount,
           COUNT(*) FILTER (WHERE cost_amount IS NOT NULL)::int AS priced,
           COUNT(*) FILTER (WHERE cost_amount IS NULL)::int AS unpriced
      FROM farm_operation_ledger
     WHERE tenant_id = $1::uuid AND season_id = $2 AND {ACTUAL_OPERATION_SQL}
     GROUP BY 1 ORDER BY 1"""

_SEASON_REVENUE_SQL = """
    SELECT upper(trim(currency)) AS currency, SUM(amount)::float AS amount, COUNT(*)::int AS rows
      FROM farm_revenue_records WHERE tenant_id = $1::uuid AND season_id = $2
     GROUP BY 1 ORDER BY 1"""

_ANNUAL_COSTS_SQL = f"""
    SELECT upper(trim(currency)) AS currency,
           SUM(cost_amount)::float AS amount,
           COUNT(*) FILTER (WHERE cost_amount IS NOT NULL)::int AS priced,
           COUNT(*) FILTER (WHERE cost_amount IS NULL)::int AS unpriced
      FROM farm_operation_ledger
     WHERE tenant_id = $1::uuid AND operation_date >= $2 AND {ACTUAL_OPERATION_SQL}
     GROUP BY 1 ORDER BY 1"""

_ANNUAL_REVENUE_SQL = """
    SELECT upper(trim(currency)) AS currency, SUM(amount)::float AS amount, COUNT(*)::int AS rows
      FROM farm_revenue_records
     WHERE tenant_id = $1::uuid AND revenue_date >= $2 AND revenue_date <= $3
     GROUP BY 1 ORDER BY 1"""

#: Water records of the field in the season: linked to a completed operation of the season,
#: or unlinked to any season and dated inside the season window. The operation filter is
#: ``ACTUAL_OPERATION_SQL`` qualified by the join alias.
_FARM_WATER_SQL = """
    SELECT w.record_date, w.water_volume_m3
      FROM farm_water_records w
      LEFT JOIN farm_operation_ledger o
        ON o.operation_id = w.operation_id AND o.tenant_id = w.tenant_id
     WHERE w.tenant_id = $1::uuid AND w.field_id = $2
       AND (o.operation_id IS NULL
            OR (o.status = 'completed' AND o.operation_date <= CURRENT_DATE))
       AND (o.season_id = $3
            OR (o.season_id IS NULL AND $4::date IS NOT NULL
                AND w.record_date >= $4::date AND w.record_date <= $5::date))"""

_WATER_LEDGER_SQL = """
    SELECT ledger_date, irrigation_mm
      FROM water_ledger
     WHERE tenant_id = $1::uuid AND field_id = $2
       AND ledger_date >= $3::date AND ledger_date <= $4::date
       AND irrigation_mm IS NOT NULL"""


def _positive_float(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 and v == v and v != float("inf") else None


def _by_currency(rows: Iterable[Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in rows:
        key = normalize_currency(r["currency"]) or "UNKNOWN"
        if r["amount"] is not None:
            out[key] = out.get(key, 0.0) + float(r["amount"])
    return out


def usd_total(
    amounts: dict[str, float], *, rows: int, unpriced: int = 0
) -> tuple[float | None, str]:
    """The USD total of a scope and why it is (not) available.

    Only a scope with recorded rows, all priced, all in USD, has a USD total.
    """
    if rows == 0:
        return None, "no_recorded_rows"
    if unpriced:
        return None, f"unpriced_operations:{unpriced}"
    currencies = sorted(amounts)
    if currencies != ["USD"]:
        return None, "currency_not_usd:" + ",".join(currencies)
    return round(amounts["USD"], 2), "ok"


def merge_season_water(
    farm_records: Iterable[tuple[date, float | None]],
    ledger_days: Iterable[tuple[date, float]],
    area_ha: float | None,
) -> dict[str, Any]:
    """Season water of one field from metered records and ``water_ledger`` depths.

    Per day: the metered volume wins; else the ledger depth (``1 mm × 1 ha = 10 m³``); a day
    whose only record is unmeasured makes the total incomplete. ``m3_ha`` is ``None`` unless the
    area is known and every day with water is measured.
    """
    metered: dict[date, float] = {}
    unmeasured: set[date] = set()
    for day, volume in farm_records:
        if volume is None:
            unmeasured.add(day)
        else:
            metered[day] = metered.get(day, 0.0) + float(volume)
    ledger: dict[date, float] = {}
    for day, mm in ledger_days:
        ledger[day] = ledger.get(day, 0.0) + float(mm)

    ledger_only = {d: mm for d, mm in ledger.items() if d not in metered}
    uncovered = sorted(d for d in unmeasured if d not in metered and d not in ledger)
    total_m3: float | None = sum(metered.values())
    if ledger_only:
        total_m3 = None if area_ha is None else total_m3 + sum(ledger_only.values()) * 10 * area_ha
    days = len(set(metered) | set(ledger_only) | set(uncovered))
    complete = not uncovered and total_m3 is not None
    m3_ha = (
        round(total_m3 / area_ha, 3)
        if complete and days and area_ha is not None and total_m3 is not None
        else None
    )
    reason = "ok"
    if not days:
        reason = "no_water_records"
    elif area_ha is None:
        reason = "field_area_unavailable"
    elif uncovered:
        reason = f"unmeasured_days:{len(uncovered)}"
    return {
        "m3_ha": m3_ha,
        "reason": reason,
        "total_m3": round(total_m3, 3) if total_m3 is not None else None,
        "days": days,
        "metered_days": len(metered),
        "ledger_days": len(ledger_only),
        "unmeasured_days": len(uncovered),
    }


async def build_governance_farm_context(
    conn,
    tenant_id: str,
    *,
    field_id: str | None = None,
    season_id: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Read the tenant's recorded farm facts into a guardrails ``farm_context``.

    Top-level guardrails keys are present only when sourced; ``provenance`` names the source of
    each, and ``unavailable`` the reason for each key that is absent.
    """
    today = today or datetime.now(UTC).date()
    ctx: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    unavailable: dict[str, str] = {}

    def emit(key: str, value: Any, source: dict[str, Any]) -> None:
        ctx[key] = value
        provenance[key] = source

    # ── field: area and water source ───────────────────────────────────────────────
    area: float | None = None
    field_row = None
    if field_id:
        field_row = await conn.fetchrow(_FIELD_SQL, tenant_id, field_id)
        if field_row is None:
            unavailable["field"] = "field_not_found_for_tenant"
    if field_row is not None:
        area = _positive_float(field_row["area_ha"])
        field_src = {"source": "fields", "field_id": field_id, "column": None}
        if area is not None:
            emit("field_area_ha", area, {**field_src, "column": "area_ha"})
        else:
            unavailable["field_area_ha"] = "area_not_recorded"
        raw_source = (field_row["water_source"] or "").strip().lower() or None
        water_class = WATER_SOURCE_CLASS.get(raw_source or "")
        if water_class:
            emit(
                "water_source",
                water_class,
                {**field_src, "column": "water_source", "recorded_value": raw_source},
            )
        else:
            unavailable["water_source"] = (
                f"unmapped_water_source:{raw_source}" if raw_source else "water_source_not_recorded"
            )
    elif not field_id:
        unavailable["field"] = "no_field_in_context"

    # ── season: costs, revenue, water ──────────────────────────────────────────────
    season = None
    if season_id:
        season = await conn.fetchrow(_SEASON_SQL, tenant_id, season_id)
        if season is None:
            unavailable["season"] = "season_not_found_for_tenant"
        elif field_id and season["field_id"] and season["field_id"] != field_id:
            unavailable["season"] = "season_not_for_field"
            season = None
    else:
        unavailable["season"] = "no_season_in_context"

    if season is not None:
        costs = await conn.fetch(_SEASON_COSTS_SQL, tenant_id, season_id)
        revenue = await conn.fetch(_SEASON_REVENUE_SQL, tenant_id, season_id)
        cost_amounts, revenue_amounts = _by_currency(costs), _by_currency(revenue)
        priced = sum(r["priced"] for r in costs)
        unpriced = sum(r["unpriced"] for r in costs)
        revenue_rows = sum(r["rows"] for r in revenue)
        season_src = {
            "season_id": season_id,
            "season_source": season["source"],
            "prediction": False,
        }
        ctx["season_economics"] = {
            **season_src,
            "costs_by_currency": cost_amounts,
            "revenue_by_currency": revenue_amounts,
            "priced_operations": priced,
            "unpriced_operations": unpriced,
            "cost_coverage": "partial" if unpriced else "recorded_operations",
            "revenue_records": revenue_rows,
            "source": ["farm_operation_ledger", "farm_revenue_records"],
        }
        value, why = usd_total(cost_amounts, rows=priced + unpriced, unpriced=unpriced)
        if value is not None:
            emit("season_costs_usd", value, {**season_src, "source": "farm_operation_ledger"})
        else:
            unavailable["season_costs_usd"] = why
        value, why = usd_total(revenue_amounts, rows=revenue_rows)
        if value is not None:
            emit("season_revenue_usd", value, {**season_src, "source": "farm_revenue_records"})
        else:
            unavailable["season_revenue_usd"] = why

        if field_id and field_row is not None:
            start, end = season["start_date"], season["end_date"] or today
            end = min(end, today)
            farm_rows = await conn.fetch(
                _FARM_WATER_SQL, tenant_id, field_id, season_id, start, end
            )
            ledger_rows = (
                await conn.fetch(_WATER_LEDGER_SQL, tenant_id, field_id, start, end)
                if start is not None
                else []
            )
            water = merge_season_water(
                [(r["record_date"], r["water_volume_m3"]) for r in farm_rows],
                [(r["ledger_date"], r["irrigation_mm"]) for r in ledger_rows],
                area,
            )
            window = {
                "from": start.isoformat() if start else None,
                "to": end.isoformat(),
            }
            ctx["season_water"] = {**water, "window": window, "field_id": field_id}
            if water["m3_ha"] is not None:
                emit(
                    "season_water_used_m3_ha",
                    water["m3_ha"],
                    {
                        **season_src,
                        "field_id": field_id,
                        "window": window,
                        "source": ["farm_water_records", "water_ledger", "fields.area_ha"],
                        "method": "metered volume per day, else water_ledger irrigation_mm x 10 x area",
                    },
                )
            else:
                unavailable["season_water_used_m3_ha"] = water["reason"]
        else:
            unavailable["season_water_used_m3_ha"] = "no_field_in_context"
    else:
        unavailable.setdefault("season_water_used_m3_ha", unavailable.get("season", ""))

    # ── trailing year, whole tenant ────────────────────────────────────────────────
    since = today - timedelta(days=ANNUAL_WINDOW_DAYS)
    annual_src = {
        "scope": "tenant",
        "window": {"from": since.isoformat(), "to": today.isoformat()},
        "prediction": False,
    }
    costs = await conn.fetch(_ANNUAL_COSTS_SQL, tenant_id, since)
    revenue = await conn.fetch(_ANNUAL_REVENUE_SQL, tenant_id, since, today)
    cost_amounts, revenue_amounts = _by_currency(costs), _by_currency(revenue)
    priced = sum(r["priced"] for r in costs)
    unpriced = sum(r["unpriced"] for r in costs)
    revenue_rows = sum(r["rows"] for r in revenue)
    ctx["annual_economics"] = {
        **annual_src,
        "costs_by_currency": cost_amounts,
        "revenue_by_currency": revenue_amounts,
        "priced_operations": priced,
        "unpriced_operations": unpriced,
        "revenue_records": revenue_rows,
    }
    value, why = usd_total(cost_amounts, rows=priced + unpriced, unpriced=unpriced)
    if value is not None:
        emit("annual_costs_usd", value, {**annual_src, "source": "farm_operation_ledger"})
    else:
        unavailable["annual_costs_usd"] = why
    value, why = usd_total(revenue_amounts, rows=revenue_rows)
    if value is not None:
        emit("annual_revenue_usd", value, {**annual_src, "source": "farm_revenue_records"})
    else:
        unavailable["annual_revenue_usd"] = why

    unavailable["cash_reserve_usd"] = NO_SERVER_SOURCE
    ctx["provenance"] = provenance
    ctx["unavailable"] = {k: v for k, v in unavailable.items() if v}
    ctx["context_schema"] = SCHEMA
    ctx["built_from"] = "server"
    return ctx


FARM_CONTEXT_TIMEOUT_S = 10.0


def threadsafe_farm_context_fn(
    loop: asyncio.AbstractEventLoop,
    open_connection: Callable[[], Any],
    tenant_id: str,
    season_id: str | None,
    *,
    timeout_s: float = FARM_CONTEXT_TIMEOUT_S,
    sink: dict | None = None,
) -> Callable[[str, str | None], dict[str, Any]]:
    """A synchronous ``farm_context_fn(tenant_id, field_id)`` for a worker thread.

    The pest-escalation workflow runs in a thread (``asyncio.to_thread``) while the database
    pool belongs to the request's event loop, so the builder is scheduled back on that loop.
    ``open_connection()`` returns an async context manager yielding a tenant-scoped connection.
    The function raises on a tenant mismatch, a timeout or a database error; the gate turns
    any exception into a block (fail closed). ``sink["farm_context"]`` keeps what was read so
    the caller can expose it in the workflow state.
    """

    async def _load(field_id: str | None) -> dict[str, Any]:
        async with open_connection() as conn:
            return await build_governance_farm_context(
                conn, tenant_id, field_id=field_id, season_id=season_id
            )

    def farm_context_fn(requested_tenant: str, field_id: str | None) -> dict[str, Any]:
        if str(requested_tenant) != str(tenant_id):
            raise PermissionError("farm_context_tenant_mismatch")
        future = asyncio.run_coroutine_threadsafe(_load(field_id), loop)
        try:
            farm = future.result(timeout=timeout_s)
        except BaseException:
            # A timeout must not leave the load holding its pooled connection: cancelling the
            # future cancels the task on the loop, which releases the connection. Still raises.
            future.cancel()
            raise
        if sink is not None:
            sink["farm_context"] = farm
        return farm

    return farm_context_fn
