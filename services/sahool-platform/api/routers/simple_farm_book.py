"""Farmer-facing simple cash/credit book over the existing farm-ledger domain."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date
from decimal import Decimal

from core.authorization import authorize
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
    task_id: uuid.UUID | None = None
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


async def _task_location(conn, tenant_id, task_id):
    row = await conn.fetchrow(
        """SELECT t.field_id, f.farm_id FROM field_tasks t JOIN fields f
             ON f.tenant_id=t.tenant_id AND f.field_id=t.field_id
           WHERE t.tenant_id=$1::uuid AND t.task_id=$2""",
        tenant_id,
        task_id,
    )
    if not row:
        raise HTTPException(404, "task_not_found_for_tenant")
    return row


async def _assert_scope(conn, tenant_id: str, req: SimpleEntryIn) -> None:
    farm = await conn.fetchval(
        "SELECT 1 FROM farms WHERE tenant_id=$1::uuid AND farm_id=$2", tenant_id, req.farm_id
    )
    if farm != 1:
        raise HTTPException(status_code=404, detail="farm_not_found_for_tenant")
    if req.field_id:
        await _assert_field_in_tenant(conn, req.field_id)
        # The field must be on the entry's farm. Checking it against the tenant alone let an
        # entry on farm X name a field of farm Y (and cite that field's receipt). A legacy
        # field with no farm recorded is not attributable to another farm and is accepted.
        field_farm = await conn.fetchval(
            "SELECT farm_id FROM fields WHERE field_id=$1", req.field_id
        )
        if field_farm is not None and field_farm != req.farm_id:
            raise HTTPException(status_code=422, detail="field_not_in_farm")
    if req.task_id is not None:
        if not req.field_id:
            raise HTTPException(status_code=422, detail="task_link_requires_field")
        scope = await _task_location(conn, tenant_id, req.task_id)
        if scope["field_id"] != req.field_id:
            raise HTTPException(status_code=422, detail="task_field_mismatch")
        if scope["farm_id"] != req.farm_id:
            raise HTTPException(status_code=422, detail="task_farm_mismatch")
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


def _receipt_field_refusal(document_field: str | None, entry_field: str | None) -> str | None:
    """The refusal code when a receipt's field does not fit the entry, else ``None``.

    A document with no field is a shared receipt (one purchase spanning fields or the whole
    farm) and fits any entry of the tenant. A document recorded on a field fits only an entry
    on that same field; a farm-level entry cannot cite a field's receipt.
    """
    document = (str(document_field or "").strip()) or None
    if document is None:
        return None
    entry = (str(entry_field or "").strip()) or None
    return None if document == entry else "receipt_field_mismatch"


def _may_link_receipt(user: UserSchema, farm_id: str | None) -> bool:
    """Linking a document is reading it: ``DOCUMENT_VIEW`` on the entry's farm.

    ``authorize`` checks the role and ``farm_ids_access``, so a user limited to other farms
    cannot attach a document to this farm's book.
    """
    return authorize(user, Permission.DOCUMENT_VIEW, farm_id=farm_id).allowed


def _may_write_on_farm(user: UserSchema, farm_id: str | None) -> bool:
    """``ACTIVITY_EXECUTE`` on the entry's farm: the role and ``farm_ids_access``.

    The route dependency checks the role only; a user limited to some farms of the tenant
    could otherwise write entries on every farm.
    """
    return authorize(user, Permission.ACTIVITY_EXECUTE, farm_id=farm_id).allowed


async def _assert_receipt(conn, tenant_id: str, req: SimpleEntryIn, user: UserSchema) -> None:
    """A receipt belongs to the entry it is attached to.

    The permission is decided on the server before the document is read. The document must
    be this tenant's and an image/report/other, and its field must fit the entry's
    (``_receipt_field_refusal``). Checked after a reversal inherits its allocation, so the
    comparison uses the field the entry is stored on.
    """
    if not req.receipt_document_id:
        return
    if not _may_link_receipt(user, req.farm_id):
        raise HTTPException(status_code=403, detail="receipt_document_permission_required")
    document = await conn.fetchrow(
        """SELECT d.field_id, f.farm_id AS field_farm_id
             FROM documents d
             LEFT JOIN fields f ON f.field_id = d.field_id
            WHERE d.tenant_id=$1::uuid AND d.doc_id=$2
              AND d.category IN ('image','report','other')""",
        tenant_id,
        req.receipt_document_id,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="receipt_document_not_found_for_tenant")
    refusal = _receipt_field_refusal(document["field_id"], req.field_id)
    if refusal:
        raise HTTPException(status_code=422, detail=refusal)
    # documents carry no farm; a field-bound receipt's farm is its field's. Authorise that farm
    # too, so the permission never rests only on the farm the caller named.
    if document["field_farm_id"] and not _may_link_receipt(user, document["field_farm_id"]):
        raise HTTPException(status_code=403, detail="receipt_document_permission_required")


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


def _inherit_task(req: SimpleEntryIn, original) -> None:
    """Keep a settlement or correction under its original task and field."""
    if req.task_id is not None and req.task_id != original["task_id"]:
        raise HTTPException(status_code=422, detail="original_task_mismatch")
    if original["task_id"] is not None:
        if req.field_id is not None and req.field_id != original["field_id"]:
            raise HTTPException(status_code=422, detail="task_field_mismatch")
        if req.farm_id != original["farm_id"]:
            raise HTTPException(status_code=422, detail="task_farm_mismatch")
        req.task_id = original["task_id"]
        req.field_id = original["field_id"]


async def _with_historical_link(conn, tenant_id, req, original):
    """Overlay a historical expense link (task_expense_links) on an original without a task."""
    if original["task_id"] is None:
        historical = await conn.fetchrow(
            "SELECT task_id, field_id FROM task_expense_links WHERE tenant_id=$1::uuid AND entry_id=$2",
            tenant_id,
            req.reverses_entry_id or req.settles_entry_id,
        )
        if historical:
            return dict(original) | dict(historical)
    return original


async def _inherit_ledger_scope(conn, tenant_id, req, original):
    original = await _with_historical_link(conn, tenant_id, req, original)
    field_id = original["field_id"]
    if (
        req.farm_id != original["farm_id"]
        or req.field_id is not None
        and req.field_id != field_id
        or req.season_id is not None
        and req.season_id != original["season_id"]
    ):
        raise HTTPException(422, "entry_scope_mismatch")
    req.field_id = field_id
    req.season_id = original["season_id"]
    _inherit_task(req, original)


async def _prepare_payment(conn, tenant_id: str, req: SimpleEntryIn) -> str:
    if not req.settles_entry_id or not req.party_id:
        raise HTTPException(status_code=422, detail="payment_requires_party_and_settled_entry")
    original = await conn.fetchrow(
        """SELECT entry_id, entry_type, payment_method, amount, currency, party_id, task_id,
                  field_id, farm_id, season_id, reverses_entry_id
           FROM farm_ledger_entries
           WHERE tenant_id=$1::uuid AND entry_id=$2 FOR UPDATE""",
        tenant_id,
        req.settles_entry_id,
    )
    if not original or original["payment_method"] != "credit":
        raise HTTPException(status_code=422, detail="settled_entry_must_be_credit")
    # A reversal (or a reversed entry) is no debt: paying it drives the party's payable
    # negative, and the report then silently nets that against the party's other debts.
    if original["reverses_entry_id"] is not None:
        raise HTTPException(status_code=422, detail="cannot_settle_a_reversal")
    if await conn.fetchval(
        """SELECT 1 FROM farm_ledger_entries
           WHERE tenant_id=$1::uuid AND reverses_entry_id=$2 LIMIT 1""",
        tenant_id,
        req.settles_entry_id,
    ):
        raise HTTPException(status_code=409, detail="cannot_settle_reversed_entry")
    if original["party_id"] != req.party_id or original["currency"] != req.currency:
        raise HTTPException(status_code=422, detail="payment_party_or_currency_mismatch")
    # A debt is the farm's: a payment booked on another farm would leave this farm's payable
    # open in its own book and drive the other farm's negative.
    if original["farm_id"] != req.farm_id:
        raise HTTPException(status_code=422, detail="payment_farm_mismatch")
    await _inherit_ledger_scope(conn, tenant_id, req, original)
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
    """Append-only correction: a reversing entry mirrors the original's type/method/
    amount/currency/party (so the DB CHECKs still hold and both net to zero in every
    total, see core.summarize_entries). Its category may be what the user typed
    («تصحيح»): reports net it under the original's category (original_category). Its
    farm/field/season are the original's: omitted ones are inherited, and a different
    one is refused (entry_scope_mismatch), so every report window cancels it where the
    original counted. It must not predate the original (entry_precedes_original) or
    itself be a settlement; each original may be reversed at most once, and a credit
    entry with payments cannot be reversed (its payable would go negative and cancel
    the party's other debts). Codes match fix/field-tasks-costs-inspection."""
    if req.settles_entry_id:
        raise HTTPException(status_code=422, detail="reversal_cannot_also_settle")
    original = await conn.fetchrow(
        """SELECT entry_type, payment_method, amount, currency, party_id, reverses_entry_id,
                  category, task_id, farm_id, field_id, season_id, occurred_on
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
    original = await _with_historical_link(conn, tenant_id, req, original)
    for column in ("farm_id", "field_id", "season_id"):
        given = getattr(req, column) or None
        if given is not None and given != (original[column] or None):
            raise HTTPException(status_code=422, detail="entry_scope_mismatch")
        setattr(req, column, original[column])
    if req.occurred_on < original["occurred_on"]:
        raise HTTPException(status_code=422, detail="entry_precedes_original")
    if await conn.fetchval(
        """SELECT 1 FROM farm_ledger_entries
           WHERE tenant_id=$1::uuid AND settles_entry_id=$2 LIMIT 1""",
        tenant_id,
        req.reverses_entry_id,
    ):
        raise HTTPException(status_code=409, detail="cannot_reverse_entry_with_settlements")
    _inherit_task(req, original)
    already = await conn.fetchval(
        """SELECT 1 FROM farm_ledger_entries
           WHERE tenant_id=$1::uuid AND reverses_entry_id=$2 LIMIT 1""",
        tenant_id,
        req.reverses_entry_id,
    )
    if already == 1:
        raise HTTPException(status_code=409, detail="entry_already_reversed")


# Entries written with v245 already carry task_id. Historical expense links are
# append-only and apply to the original plus its existing and future children.
_LINK_JOIN = """LEFT JOIN task_expense_links link ON link.tenant_id=e.tenant_id
    AND link.entry_id=COALESCE(e.reverses_entry_id,e.settles_entry_id,e.entry_id)"""
_EFFECTIVE_TASK = "COALESCE(e.task_id, link.task_id)"
_EFFECTIVE_FIELD = "COALESCE(e.field_id, link.field_id)"


_REPLAY_ENTRY = f"""SELECT e.entry_id, e.client_operation_id, e.request_digest, e.sync_status,
                           {_EFFECTIVE_TASK} AS task_id
                    FROM farm_ledger_entries e {_LINK_JOIN}
                    WHERE e.tenant_id=$1::uuid AND e.client_operation_id=$2"""


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
    if not _may_write_on_farm(user, req.farm_id):
        raise HTTPException(status_code=403, detail="farm_access_denied")
    entry_id = "fbe_" + uuid.uuid4().hex[:18]
    tenant_id = str(user.tenant_id)
    request_digest = hashlib.sha256(
        json.dumps(
            req.model_dump(mode="json", exclude={"task_id"} if req.task_id is None else set()),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    replayed = False
    try:
        async with tenant_connection(user) as conn:
            async with conn.transaction():
                # Serialize identical operation keys before checking settlement/reversal state.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"{tenant_id}:{req.client_operation_id}",
                )
                existing = await conn.fetchrow(
                    _REPLAY_ENTRY,
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
                    if req.reverses_entry_id:
                        await _assert_reversal(conn, tenant_id, req)
                    direction = (
                        await _prepare_payment(conn, tenant_id, req)
                        if req.entry_type == "payment"
                        else ("outflow" if req.entry_type == "expense" else "inflow")
                    )
                    # Scope, then receipt, on the allocation a reversal or payment inherited.
                    await _assert_scope(conn, tenant_id, req)
                    await _assert_receipt(conn, tenant_id, req, user)
                    row = await conn.fetchrow(
                        """INSERT INTO farm_ledger_entries
                           (entry_id,tenant_id,client_operation_id,request_digest,entry_type,direction,
                            payment_method,category,amount,currency,occurred_on,farm_id,field_id,
                            season_id,party_id,settles_entry_id,reverses_entry_id,quantity,unit,
                            description,receipt_document_id,source,sync_status,created_by,task_id)
                           VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                                   $17,$18,$19,$20,$21,$22,'synced',$23,$24)
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
                        req.task_id,
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
                    _REPLAY_ENTRY,
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
        "task_id": row["task_id"],
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
    task_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> tuple[str, list]:
    args: list = [tenant_id]
    clauses = ["e.tenant_id=$1::uuid"]
    for column, value in (
        ("farm_id", farm_id),
        ("field_id", field_id),
        ("season_id", season_id),
        ("task_id", task_id),
    ):
        if value:
            # A reversing row is allocated where its original is (``orig``, joined in
            # _fetch_entries), so a legacy reversal stored elsewhere still cancels it.
            args.append(value)
            if column == "field_id":
                # task_expense_links (v245) carries a historical expense's field.
                own, from_original = _EFFECTIVE_FIELD, "COALESCE(orig.field_id, link.field_id)"
            elif column == "task_id":
                own, from_original = _EFFECTIVE_TASK, "COALESCE(orig.task_id, link.task_id)"
            else:
                own, from_original = f"e.{column}", f"orig.{column}"
            clauses.append(
                f"(CASE WHEN orig.entry_id IS NULL THEN {own} ELSE {from_original} END)"
                f"=${len(args)}"
            )
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
        f"""SELECT e.*, {_EFFECTIVE_TASK} AS task_id, {_EFFECTIVE_FIELD} AS field_id,
                   p.name AS party_name, settled.entry_type AS settled_entry_type,
                   orig.category AS original_category
            FROM farm_ledger_entries e {_LINK_JOIN}
            LEFT JOIN farm_ledger_parties p
              ON p.tenant_id=e.tenant_id AND p.party_id=e.party_id
            LEFT JOIN farm_ledger_entries settled
              ON settled.tenant_id=e.tenant_id AND settled.entry_id=e.settles_entry_id
            LEFT JOIN farm_ledger_entries orig
              ON orig.tenant_id=e.tenant_id AND orig.entry_id=e.reverses_entry_id
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
    task_id: uuid.UUID | None = None,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_VIEW)),
):
    where, args = _entry_filters(
        str(user.tenant_id),
        farm_id=farm_id,
        field_id=field_id,
        season_id=season_id,
        task_id=task_id,
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
    task_id: uuid.UUID | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    start, end = _month_bounds(month)
    where, args = _entry_filters(
        str(user.tenant_id),
        farm_id=farm_id,
        field_id=field_id,
        season_id=season_id,
        task_id=task_id,
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
        "summary": summarize_entries(
            entries, area_ha=float(area) if area else None, by_currency=True
        ),
    }


@router.get("/api/v1/farm-book/balances")
async def book_balances(
    farm_id: str | None = None,
    field_id: str | None = None,
    season_id: str | None = None,
    task_id: uuid.UUID | None = None,
    as_of: date | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    where, args = _entry_filters(
        str(user.tenant_id),
        farm_id=farm_id,
        field_id=field_id,
        season_id=season_id,
        task_id=task_id,
        date_from=None,
        date_to=as_of,
    )
    async with tenant_connection(user) as conn:
        entries = await _fetch_entries(conn, where, args)
    return {
        "as_of": as_of.isoformat() if as_of else None,
        "summary": summarize_entries(entries, by_currency=True),
    }


@router.get("/api/v1/farm-book/export")
async def export_book(
    month: str,
    format: str = Query("csv", pattern="^(csv|pdf)$"),
    farm_id: str | None = None,
    field_id: str | None = None,
    season_id: str | None = None,
    task_id: uuid.UUID | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    start, end = _month_bounds(month)
    where, args = _entry_filters(
        str(user.tenant_id),
        farm_id=farm_id,
        field_id=field_id,
        season_id=season_id,
        task_id=task_id,
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
