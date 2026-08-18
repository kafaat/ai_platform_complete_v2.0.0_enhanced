"""S3 historical-weather SoR and S11 ERP reconciliation APIs."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from core.operational_truth import content_digest, reconciliation_status
from core.erp_projection_contract import verify_reconciliation_binding
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from api.main import (
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()


class HistoricalWeatherPayload(BaseModel):
    tmax_c: float | None = None
    tmin_c: float | None = None
    tmean_c: float | None = None
    humidity_pct: float | None = Field(None, ge=0, le=100)
    precipitation_mm: float | None = Field(None, ge=0)
    wind_speed_m_s: float | None = Field(None, ge=0)
    solar_radiation_mj_m2: float | None = Field(None, ge=0)
    et0_mm: float | None = Field(None, ge=0)
    gdd: float | None = Field(None, ge=0)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def at_least_one_measurement(self):
        measurements = self.model_dump(exclude={"provider_metadata"})
        if not any(value is not None for value in measurements.values()):
            raise ValueError("at least one historical weather measurement is required")
        if self.tmax_c is not None and self.tmin_c is not None and self.tmax_c < self.tmin_c:
            raise ValueError("tmax_c must be greater than or equal to tmin_c")
        return self


class HistoricalWeatherIn(BaseModel):
    source_record_id: str = Field(min_length=1, max_length=180)
    field_id: str
    season_id: str | None = None
    observed_on: date
    available_at: datetime
    source: str = Field(min_length=1, max_length=80)
    quality: str = "provisional"
    payload: HistoricalWeatherPayload
    supersedes_record_id: str | None = None

    @field_validator("quality")
    @classmethod
    def valid_quality(cls, value: str) -> str:
        if value not in {"validated", "provisional", "suspect"}:
            raise ValueError("quality must be validated|provisional|suspect")
        return value

    @field_validator("available_at")
    @classmethod
    def available_at_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("available_at must include a timezone")
        return value


class ERPReconciliationIn(BaseModel):
    outbox_id: str
    provider: str = Field(min_length=1, max_length=80)
    provider_event_id: str = Field(min_length=1, max_length=180)
    external_reference: str | None = Field(None, max_length=180)
    status: str
    expected_amount: Decimal | None = Field(None, max_digits=18, decimal_places=2)
    actual_amount: Decimal | None = Field(None, max_digits=18, decimal_places=2)
    currency: str | None = Field(None, min_length=3, max_length=3)
    evidence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in {"matched", "difference", "rejected"}:
            raise ValueError("status must be matched|difference|rejected")
        return value


@router.post("/api/v1/weather/history/records", status_code=201)
async def ingest_historical_weather(
    req: HistoricalWeatherIn,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_EXECUTE)),
):
    tenant_id = str(user.tenant_id)
    digest_payload = req.model_dump(mode="json", exclude={"supersedes_record_id"})
    digest = content_digest(digest_payload)
    record_id = "hwd_" + uuid.uuid4().hex[:20]
    try:
        async with tenant_connection(user) as conn:
            async with conn.transaction():
                await _assert_field_in_tenant(conn, req.field_id)
                if req.season_id:
                    season = await conn.fetchval(
                        """SELECT 1 FROM seasons
                           WHERE tenant_id=$1::uuid AND season_id=$2 AND field_id=$3
                           UNION ALL
                           SELECT 1 FROM farm_season_projects
                           WHERE tenant_id=$1::uuid AND season_id=$2 AND field_id=$3
                           LIMIT 1""",
                        tenant_id,
                        req.season_id,
                        req.field_id,
                    )
                    if season != 1:
                        raise HTTPException(status_code=404, detail="season_not_found_for_field")
                existing = await conn.fetchrow(
                    """SELECT record_id, content_hash FROM historical_weather_daily
                       WHERE tenant_id=$1::uuid AND source=$2 AND source_record_id=$3""",
                    tenant_id,
                    req.source,
                    req.source_record_id,
                )
                if existing:
                    if existing["content_hash"] != digest:
                        raise HTTPException(
                            status_code=409, detail="source_record_payload_conflict"
                        )
                    return {"record_id": existing["record_id"], "persisted": True, "replayed": True}
                if req.supersedes_record_id:
                    superseded = await conn.fetchval(
                        """SELECT 1 FROM historical_weather_daily
                           WHERE tenant_id=$1::uuid AND record_id=$2 AND field_id=$3""",
                        tenant_id,
                        req.supersedes_record_id,
                        req.field_id,
                    )
                    if superseded != 1:
                        raise HTTPException(status_code=404, detail="superseded_record_not_found")
                await conn.execute(
                    """INSERT INTO historical_weather_daily
                       (record_id,tenant_id,field_id,season_id,observed_on,available_at,source,
                        source_record_id,quality,payload,content_hash,supersedes_record_id,ingested_by)
                       VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11,$12,$13)""",
                    record_id,
                    tenant_id,
                    req.field_id,
                    req.season_id,
                    req.observed_on,
                    req.available_at,
                    req.source,
                    req.source_record_id,
                    req.quality,
                    json.dumps(req.payload.model_dump(mode="json"), ensure_ascii=False),
                    digest,
                    req.supersedes_record_id,
                    str(user.user_id),
                )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("حفظ سجل الطقس التاريخي", exc) from exc
    return {"record_id": record_id, "persisted": True, "replayed": False}


@router.get("/api/v1/weather/history/records")
async def read_historical_weather(
    field_id: str,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    as_known_at: datetime | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    args: list[Any] = [str(user.tenant_id), field_id]
    if as_known_at is not None and (as_known_at.tzinfo is None or as_known_at.utcoffset() is None):
        raise HTTPException(status_code=422, detail="as_known_at_must_include_timezone")
    clauses = ["tenant_id=$1::uuid", "field_id=$2"]
    for column, value, operator in (
        ("observed_on", date_from, ">="),
        ("observed_on", date_to, "<="),
        ("available_at", as_known_at, "<="),
    ):
        if value is not None:
            args.append(value)
            clauses.append(f"{column}{operator}${len(args)}")
    async with tenant_connection(user) as conn:
        await _assert_field_in_tenant(conn, field_id)
        rows = await conn.fetch(
            f"""SELECT * FROM historical_weather_daily
                WHERE {" AND ".join(clauses)}
                ORDER BY observed_on, available_at""",
            *args,
        )
    return {"field_id": field_id, "as_known_at": as_known_at, "items": [dict(r) for r in rows]}


@router.get("/api/v1/weather/history/coverage")
async def historical_weather_coverage(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    async with tenant_connection(user) as conn:
        await _assert_field_in_tenant(conn, field_id)
        row = await conn.fetchrow(
            """SELECT min(observed_on) AS first_day, max(observed_on) AS last_day,
                      count(DISTINCT observed_on) AS day_count,
                      array_agg(DISTINCT source ORDER BY source) AS sources
               FROM historical_weather_daily
               WHERE tenant_id=$1::uuid AND field_id=$2""",
            str(user.tenant_id),
            field_id,
        )
    return dict(row)


@router.post("/api/v1/erp/reconciliations", status_code=201)
async def record_erp_reconciliation(
    req: ERPReconciliationIn,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_EXECUTE)),
):
    try:
        reconciliation_status(req.expected_amount, req.actual_amount, req.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    tenant_id = str(user.tenant_id)
    digest = content_digest(req.model_dump(mode="json"))
    reconciliation_id = "erpr_" + uuid.uuid4().hex[:20]
    try:
        async with tenant_connection(user) as conn:
            existing = await conn.fetchrow(
                """SELECT reconciliation_id, content_hash FROM erp_reconciliation_ledger
                   WHERE tenant_id=$1::uuid AND provider=$2 AND provider_event_id=$3""",
                tenant_id,
                req.provider,
                req.provider_event_id,
            )
            if existing:
                if existing["content_hash"] != digest:
                    raise HTTPException(status_code=409, detail="provider_event_payload_conflict")
                return {
                    "reconciliation_id": existing["reconciliation_id"],
                    "persisted": True,
                    "replayed": True,
                }
            outbox = await conn.fetchrow(
                """SELECT provider, payload, status, sent_at FROM farm_ledger_erp_projection_outbox
                   WHERE tenant_id=$1::uuid AND outbox_id=$2""",
                tenant_id,
                req.outbox_id,
            )
            if outbox is None:
                raise HTTPException(status_code=404, detail="erp_projection_outbox_not_found")
            payload = outbox["payload"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except (TypeError, ValueError) as exc:
                    raise HTTPException(status_code=409, detail="erp_projection_payload_invalid") from exc
            try:
                verify_reconciliation_binding(
                    stored_payload=payload,
                    stored_provider=str(outbox["provider"]),
                    stored_status=str(outbox["status"]),
                    stored_sent_at=outbox["sent_at"],
                    receipt_provider=req.provider,
                    evidence=req.evidence,
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            await conn.execute(
                """INSERT INTO erp_reconciliation_ledger
                   (reconciliation_id,tenant_id,outbox_id,provider,provider_event_id,
                    external_reference,status,expected_amount,actual_amount,currency,evidence,
                    content_hash,reconciled_by)
                   VALUES ($1,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12,$13)""",
                reconciliation_id,
                tenant_id,
                req.outbox_id,
                req.provider,
                req.provider_event_id,
                req.external_reference,
                req.status,
                req.expected_amount,
                req.actual_amount,
                req.currency.upper() if req.currency else None,
                json.dumps(req.evidence, ensure_ascii=False),
                digest,
                str(user.user_id),
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("حفظ مصالحة ERP", exc) from exc
    return {"reconciliation_id": reconciliation_id, "persisted": True, "replayed": False}


@router.get("/api/v1/erp/reconciliations")
async def list_erp_reconciliations(
    outbox_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    args: list[Any] = [str(user.tenant_id)]
    where = "tenant_id=$1::uuid"
    if outbox_id:
        args.append(outbox_id)
        where += f" AND outbox_id=${len(args)}"
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            f"""SELECT * FROM erp_reconciliation_ledger
                WHERE {where} ORDER BY reconciled_at DESC LIMIT 1000""",
            *args,
        )
    return {"items": [dict(r) for r in rows], "count": len(rows)}
