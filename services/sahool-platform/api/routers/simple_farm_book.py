"""Farmer-facing simple cash/credit book over the existing farm-ledger domain."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date
from decimal import Decimal

from core.simple_farm_book import entries_csv, monthly_pdf, summarize_entries
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from api.main import (
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_ENTRY_TYPES = {"expense", "income", "payment"}
_PAYMENT_METHODS = {"cash", "credit"}
_PARTY_TYPES = {"supplier", "customer", "both"}


class PartyIn(BaseModel):
    party_id: str | None = None
    party_type: str
    name: str = Field(min_length=1, max_length=160)
    phone: str | None = Field(None, max_length=40)
    notes: str | None = Field(None, max_length=1000)

    @field_validator("party_type")
    @classmethod
    def _party_type(cls, value: str) -> str:
        if value not in _PARTY_TYPES:
            raise ValueError("party_type must be supplier|customer|both")
        return value


class SimpleEntryIn(BaseModel):
    client_operation_id: str = Field(min_length=8, max_length=120)
    entry_type: str
    payment_method: str = "cash"
    category: str = Field(min_length=1, max_length=80)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="YER", min_length=3, max_length=3)
    occurred_on: date
    farm_id: str
    field_id: str | None = None
    season_id: str | None = None
    party_id: str | None = None
    settles_entry_id: str | None = None
    reverses_entry_id: str | None = None
    quantity: Decimal | None = Field(None, gt=0, max_digits=18, decimal_places=3)
    unit: str | None = Field(None, max_length=30)
    description: str | None = Field(None, max_length=2000)
    receipt_document_id: str | None = Field(None, max_length=50)
    source: str = Field(default="manual_mobile", max_length=50)

    @field_validator("entry_type")
    @classmethod
    def _entry_type(cls, value: str) -> str:
        if value not in _ENTRY_TYPES:
            raise ValueError("entry_type must be expense|income|payment")
        return value

    @field_validator("payment_method")
    @classmethod
    def _payment_method(cls, value: str) -> str:
        if value not in _PAYMENT_METHODS:
            raise ValueError("payment_method must be cash|credit")
        return value

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str) -> str:
        value = value.upper()
        if not value.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return value


async def _assert_scope(conn, tenant_id: str, req: SimpleEntryIn) -> None:
    farm = await conn.fetchval(
        "SELECT 1 FROM farms WHERE tenant_id=$1::uuid AND farm_id=$2", tenant_id, req.farm_id
    )
    if farm != 1:
        raise HTTPException(status_code=404, detail="farm_not_found_for_tenant")
    if req.field_id:
        await _assert_field_in_tenant(conn, req.field_id)
    if req.season_id:
        season = await conn.fetchval(
            """SELECT 1 FROM seasons WHERE tenant_id=$1::uuid AND season_id=$2
               UNION ALL
               SELECT 1 FROM farm_season_projects WHERE tenant_id=$1::uuid AND season_id=$2
               LIMIT 1""",
            tenant_id,
            req.season_id,
        )
        if season != 1:
            raise HTTPException(status_code=404, detail="season_not_found_for_tenant")
    if req.party_id:
        party = await conn.fetchval(
            "SELECT 1 FROM farm_ledger_parties WHERE tenant_id=$1::uuid AND party_id=$2",
            tenant_id,
            req.party_id,
        )
        if party != 1:
            raise HTTPException(status_code=404, detail="party_not_found_for_tenant")
    if req.receipt_document_id:
        document = await conn.fetchval(
            """SELECT 1 FROM documents
               WHERE tenant_id=$1::uuid AND doc_id=$2
                 AND category IN ('image','report','other')""",
            tenant_id,
            req.receipt_document_id,
        )
        if document != 1:
            raise HTTPException(status_code=404, detail="receipt_document_not_found_for_tenant")


@router.post("/api/v1/farm-book/parties", status_code=201)
async def create_party(
    req: PartyIn,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_EXECUTE)),
):
    party_id = req.party_id or "party_" + uuid.uuid4().hex[:16]
    try:
        async with tenant_connection(user) as conn:
            await conn.execute(
                """INSERT INTO farm_ledger_parties
                   (party_id, tenant_id, party_type, name, phone, notes, created_by)
                   VALUES ($1,$2::uuid,$3,$4,$5,$6,$7)
                   ON CONFLICT (tenant_id, party_id) DO NOTHING""",
                party_id,
                str(user.tenant_id),
                req.party_type,
                req.name.strip(),
                req.phone,
                req.notes,
                str(user.user_id),
            )
            row = await conn.fetchrow(
                """SELECT party_id, party_type, name, phone, notes, created_at
                   FROM farm_ledger_parties WHERE tenant_id=$1::uuid AND party_id=$2""",
                str(user.tenant_id),
                party_id,
            )
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("حفظ المورد أو العميل", exc) from exc
    return {**dict(row), "created_at": row["created_at"].isoformat()}


@router.get("/api/v1/farm-book/parties")
async def list_parties(
    party_type: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_VIEW)),
):
    if party_type and party_type not in _PARTY_TYPES:
        raise HTTPException(status_code=422, detail="invalid_party_type")
    args: list = [str(user.tenant_id)]
    where = "tenant_id=$1::uuid"
    if party_type:
        args.append(party_type)
        where += f" AND (party_type=${len(args)} OR party_type='both')"
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            f"""SELECT party_id, party_type, name, phone, notes, created_at
                FROM farm_ledger_parties WHERE {where} ORDER BY name LIMIT 500""",
            *args,
        )
    return {
        "items": [dict(r) | {"created_at": r["created_at"].isoformat()} for r in rows],
        "count": len(rows),
    }


async def _prepare_payment(conn, tenant_id: str, req: SimpleEntryIn) -> str:
    if not req.settles_entry_id or not req.party_id:
        raise HTTPException(status_code=422, detail="payment_requires_party_and_settled_entry")
    original = await conn.fetchrow(
        """SELECT entry_id, entry_type, payment_method, amount, currency, party_id
           FROM farm_ledger_entries
           WHERE tenant_id=$1::uuid AND entry_id=$2 FOR UPDATE""",
        tenant_id,
        req.settles_entry_id,
    )
    if not original or original["payment_method"] != "credit":
        raise HTTPException(status_code=422, detail="settled_entry_must_be_credit")
    if original["party_id"] != req.party_id or original["currency"] != req.currency:
        raise HTTPException(status_code=422, detail="payment_party_or_currency_mismatch")
    paid = await conn.fetchval(
        """SELECT COALESCE(SUM(amount),0) FROM farm_ledger_entries
           WHERE tenant_id=$1::uuid AND settles_entry_id=$2""",
        tenant_id,
        req.settles_entry_id,
    )
    if Decimal(str(paid)) + req.amount > Decimal(str(original["amount"])):
        raise HTTPException(status_code=409, detail="payment_exceeds_remaining_debt")
    return "outflow" if original["entry_type"] == "expense" else "inflow"


async def _assert_reversal(conn, tenant_id: str, req: SimpleEntryIn) -> None:
    """Append-only correction: a reversing entry mirrors the original exactly and both
    net to zero in every total (see core.summarize_entries). The mirror must match the
    original's type/method/amount/currency so the DB CHECKs still hold, must not itself
    be a settlement, and each original may be reversed at most once."""
    if req.settles_entry_id:
        raise HTTPException(status_code=422, detail="reversal_cannot_also_settle")
    original = await conn.fetchrow(
        """SELECT entry_type, payment_method, amount, currency, party_id, reverses_entry_id
           FROM farm_ledger_entries
           WHERE tenant_id=$1::uuid AND entry_id=$2 FOR UPDATE""",
        tenant_id,
        req.reverses_entry_id,
    )
    if not original:
        raise HTTPException(status_code=404, detail="reversed_entry_not_found")
    if original["reverses_entry_id"] is not None:
        raise HTTPException(status_code=422, detail="cannot_reverse_a_reversal")
    if (
        original["entry_type"] != req.entry_type
        or original["payment_method"] != req.payment_method
        or Decimal(str(original["amount"])) != req.amount
        or original["currency"] != req.currency
        or (original["party_id"] or None) != (req.party_id or None)
    ):
        raise HTTPException(status_code=422, detail="reversal_must_mirror_original")
    already = await conn.fetchval(
        """SELECT 1 FROM farm_ledger_entries
           WHERE tenant_id=$1::uuid AND reverses_entry_id=$2 LIMIT 1""",
        tenant_id,
        req.reverses_entry_id,
    )
    if already == 1:
        raise HTTPException(status_code=409, detail="entry_already_reversed")


@router.post("/api/v1/farm-book/entries", status_code=201)
async def create_entry(
    req: SimpleEntryIn,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_EXECUTE)),
):
    import asyncpg

    if req.payment_method == "credit" and not req.party_id:
        raise HTTPException(status_code=422, detail="credit_requires_party")
    if req.entry_type == "payment" and req.payment_method != "cash":
        raise HTTPException(status_code=422, detail="payment_must_be_cash")
    if req.entry_type != "payment" and req.settles_entry_id:
        raise HTTPException(status_code=422, detail="only_payment_can_settle_entry")
    if req.reverses_entry_id and req.entry_type == "payment":
        raise HTTPException(status_code=422, detail="payment_cannot_be_a_reversal")
    entry_id = "fbe_" + uuid.uuid4().hex[:18]
    tenant_id = str(user.tenant_id)
    request_digest = hashlib.sha256(
        json.dumps(req.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    replayed = False
    try:
        async with tenant_connection(user) as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    """SELECT * FROM farm_ledger_entries
                       WHERE tenant_id=$1::uuid AND client_operation_id=$2""",
                    tenant_id,
                    req.client_operation_id,
                )
                if existing:
                    if existing["request_digest"] != request_digest:
                        raise HTTPException(
                            status_code=409, detail="client_operation_id_payload_conflict"
                        )
                    replayed = True
                    row = existing
                else:
                    await _assert_scope(conn, tenant_id, req)
                    if req.reverses_entry_id:
                        await _assert_reversal(conn, tenant_id, req)
                    direction = (
                        await _prepare_payment(conn, tenant_id, req)
                        if req.entry_type == "payment"
                        else ("outflow" if req.entry_type == "expense" else "inflow")
                    )
                    row = await conn.fetchrow(
                        """INSERT INTO farm_ledger_entries
                           (entry_id,tenant_id,client_operation_id,request_digest,entry_type,direction,
                            payment_method,category,amount,currency,occurred_on,farm_id,field_id,
                            season_id,party_id,settles_entry_id,reverses_entry_id,quantity,unit,
                            description,receipt_document_id,source,sync_status,created_by)
                           VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                                   $17,$18,$19,$20,$21,$22,'synced',$23)
                           RETURNING *""",
                        entry_id,
                        tenant_id,
                        req.client_operation_id,
                        request_digest,
                        req.entry_type,
                        direction,
                        req.payment_method,
                        req.category,
                        req.amount,
                        req.currency,
                        req.occurred_on,
                        req.farm_id,
                        req.field_id,
                        req.season_id,
                        req.party_id,
                        req.settles_entry_id,
                        req.reverses_entry_id,
                        req.quantity,
                        req.unit,
                        req.description,
                        req.receipt_document_id,
                        req.source,
                        str(user.user_id),
                    )
    except HTTPException:
        raise
    except asyncpg.UniqueViolationError:
        # Idempotency race: a concurrent request with the same client_operation_id won
        # the INSERT. Resolve idempotently — re-read the persisted row on a fresh
        # connection (409 only on a genuine payload conflict), never a spurious 503.
        try:
            async with tenant_connection(user) as conn:
                row = await conn.fetchrow(
                    """SELECT * FROM farm_ledger_entries
                       WHERE tenant_id=$1::uuid AND client_operation_id=$2""",
                    tenant_id,
                    req.client_operation_id,
                )
        except Exception as exc:  # noqa: BLE001
            raise _db_unavailable("حفظ القيد المالي المبسط", exc) from exc
        if row is None:
            # The unique violation was on some other constraint, not the idempotency key.
            raise HTTPException(status_code=409, detail="entry_constraint_conflict") from None
        if row["request_digest"] != request_digest:
            raise HTTPException(
                status_code=409, detail="client_operation_id_payload_conflict"
            ) from None
        replayed = True
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("حفظ القيد المالي المبسط", exc) from exc
    return {
        "entry_id": row["entry_id"],
        "client_operation_id": row["client_operation_id"],
        "persisted": True,
        "replayed": replayed,
        "sync_status": row["sync_status"],
    }


def _entry_filters(
    tenant_id: str,
    *,
    farm_id: str | None,
    field_id: str | None,
    season_id: str | None,
    date_from: date | None,
    date_to: date | None,
) -> tuple[str, list]:
    args: list = [tenant_id]
    clauses = ["e.tenant_id=$1::uuid"]
    for column, value in (
        ("farm_id", farm_id),
        ("field_id", field_id),
        ("season_id", season_id),
    ):
        if value:
            args.append(value)
            clauses.append(f"e.{column}=${len(args)}")
    if date_from:
        args.append(date_from)
        clauses.append(f"e.occurred_on>=${len(args)}")
    if date_to:
        args.append(date_to)
        clauses.append(f"e.occurred_on<=${len(args)}")
    return " AND ".join(clauses), args


async def _fetch_entries(conn, where: str, args: list, *, limit: int | None = None) -> list[dict]:
    limit_sql = ""
    query_args = list(args)
    if limit is not None:
        query_args.append(limit)
        limit_sql = f" LIMIT ${len(query_args)}"
    rows = await conn.fetch(
        f"""SELECT e.*, p.name AS party_name, settled.entry_type AS settled_entry_type
            FROM farm_ledger_entries e
            LEFT JOIN farm_ledger_parties p
              ON p.tenant_id=e.tenant_id AND p.party_id=e.party_id
            LEFT JOIN farm_ledger_entries settled
              ON settled.tenant_id=e.tenant_id AND settled.entry_id=e.settles_entry_id
            WHERE {where}
            ORDER BY e.occurred_on DESC, e.created_at DESC{limit_sql}""",
        *query_args,
    )
    return [
        dict(r)
        | {
            "amount": float(r["amount"]),
            "quantity": float(r["quantity"]) if r["quantity"] is not None else None,
            "occurred_on": r["occurred_on"].isoformat(),
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


@router.get("/api/v1/farm-book/entries")
async def list_entries(
    farm_id: str | None = None,
    field_id: str | None = None,
    season_id: str | None = None,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_VIEW)),
):
    where, args = _entry_filters(
        str(user.tenant_id),
        farm_id=farm_id,
        field_id=field_id,
        season_id=season_id,
        date_from=date_from,
        date_to=date_to,
    )
    async with tenant_connection(user) as conn:
        if field_id:
            await _assert_field_in_tenant(conn, field_id)
        items = await _fetch_entries(conn, where, args, limit=2000)
    return {"items": items, "count": len(items)}


def _month_bounds(month: str) -> tuple[date, date]:
    if not _MONTH.fullmatch(month):
        raise HTTPException(status_code=422, detail="month_must_be_yyyy_mm")
    year, number = map(int, month.split("-"))
    start = date(year, number, 1)
    end = date(year + 1 if number == 12 else year, 1 if number == 12 else number + 1, 1)
    return start, end


@router.get("/api/v1/farm-book/monthly")
async def monthly_report(
    month: str,
    farm_id: str | None = None,
    field_id: str | None = None,
    season_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    start, end = _month_bounds(month)
    where, args = _entry_filters(
        str(user.tenant_id),
        farm_id=farm_id,
        field_id=field_id,
        season_id=season_id,
        date_from=start,
        date_to=None,
    )
    args.append(end)
    where += f" AND e.occurred_on<${len(args)}"
    async with tenant_connection(user) as conn:
        if field_id:
            await _assert_field_in_tenant(conn, field_id)
        entries = await _fetch_entries(conn, where, args)
        area = None
        if field_id:
            area = await conn.fetchval(
                "SELECT area_ha FROM fields WHERE tenant_id=$1::uuid AND field_id=$2",
                str(user.tenant_id),
                field_id,
            )
    return {
        "month": month,
        "summary": summarize_entries(entries, area_ha=float(area) if area else None),
    }


@router.get("/api/v1/farm-book/balances")
async def book_balances(
    farm_id: str | None = None,
    field_id: str | None = None,
    season_id: str | None = None,
    as_of: date | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    where, args = _entry_filters(
        str(user.tenant_id),
        farm_id=farm_id,
        field_id=field_id,
        season_id=season_id,
        date_from=None,
        date_to=as_of,
    )
    async with tenant_connection(user) as conn:
        entries = await _fetch_entries(conn, where, args)
    return {"as_of": as_of.isoformat() if as_of else None, "summary": summarize_entries(entries)}


@router.get("/api/v1/farm-book/export")
async def export_book(
    month: str,
    format: str = Query("csv", pattern="^(csv|pdf)$"),
    farm_id: str | None = None,
    field_id: str | None = None,
    season_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    start, end = _month_bounds(month)
    where, args = _entry_filters(
        str(user.tenant_id),
        farm_id=farm_id,
        field_id=field_id,
        season_id=season_id,
        date_from=start,
        date_to=None,
    )
    args.append(end)
    where += f" AND e.occurred_on<${len(args)}"
    async with tenant_connection(user) as conn:
        entries = await _fetch_entries(conn, where, args)
    if format == "csv":
        body = entries_csv(entries)
        media = "text/csv; charset=utf-8"
        filename = f"farm_book_{month}.csv"
    else:
        summary = summarize_entries(entries)
        try:
            body = monthly_pdf(entries, summary, f"SAHOOL Farm Book {month}")
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        media = "application/pdf"
        filename = f"farm_book_{month}.pdf"
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
