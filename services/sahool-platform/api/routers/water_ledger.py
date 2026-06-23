"""api/routers/water_ledger.py — دفتر المياه اليوميّ المُخزَّن القابل للتدقيق
==============================================================================
الفجوة #1 من إلهام IrriPro / FAO-56 (``sahool-brain/decisions/water-intelligence
-direction.md``): SAHOOL يملك نواة ريّ شبه كاملة لكنّ قرار الريّ يُحسَب ويُعرَض
ويُنسى — **لا دفتر يوميّ مُسجَّل/مُدقَّق**. هذا الموجِّه يُدِيم «دفتر مياه يوميّ»
لكلّ حقل: صفّ لكلّ (حقل، يوم) يحمل ET0/Kc/ETc/مطر/ريّ/رطوبة/عجز/مرحلة/قرار/ثقة،
فيجعل قرار الريّ قابلاً للتدقيق والتكرار.

صدق منهجيّ صارم (نمط ``decision_record``): هذا **تخزين/تدقيق** لقيم تُمرَّر من
المستدعي (أو محسوبة بمحرّكات FAO-56 القائمة ``core/engines/``) — **لا اختراع
أرقام**. الحقول الناقصة ⇒ ``NULL`` (لا تلفيق). لا نُعيد بناء نواة الريّ هنا.

النقاط (v98، جدول ``water_ledger`` معزول بالمستأجِر، RLS):
  • POST /api/v1/fields/{field_id}/water-ledger — upsert صفّ يوميّ (FIELD_EDIT)،
    idempotent عبر ``ON CONFLICT (field_id, ledger_date) DO UPDATE``.
  • GET  /api/v1/fields/{field_id}/water-ledger?from=&to= — سلسلة مرتّبة بالتاريخ
    (FIELD_VIEW)، معزولة RLS.

نمط الاستيراد من ``api.main`` يطابق ``routers/prescriptions.py`` تماماً: التبعيّات
(``get_current_user``/``UserSchema``/RLS) تبقى في ``main`` ويستوردها هذا الموجِّه؛
و``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد تعريف كلّ التبعيّات) فيُحلّ
الاستيراد الدائريّ. SQL بارامتريّ بالكامل (لا حقن).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from api.main import (
    _DB_POOL,
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.water_ledger_compute import (
    LEDGER_SELECT_COLS,
    normalize_ledger_input,
    parse_ledger_date,
    row_to_ledger_entry,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── النماذج ─────────────────────────────────────────────────────


class WaterLedgerUpsertRequest(BaseModel):
    """قيد دفتر مياه يوميّ واحد. ``ledger_date`` (YYYY-MM-DD) مفتاح idempotency.

    كلّ القيم الرقميّة اختياريّة: الناقص يبقى ``None`` ⇒ ``NULL`` (لا تلفيق).
    """

    ledger_date: str = Field(..., min_length=1, description="يوم الدفتر (YYYY-MM-DD)")
    et0_mm: float | None = None
    kc: float | None = None
    etc_mm: float | None = None
    rain_mm: float | None = None
    irrigation_mm: float | None = None
    soil_moisture_pct: float | None = None
    depletion_mm: float | None = None
    deficit_mm: float | None = None
    stage: str | None = None
    decision: str | None = None
    confidence: float | None = None


@router.post("/api/v1/fields/{field_id}/water-ledger")
async def upsert_water_ledger(
    req: WaterLedgerUpsertRequest,
    field_id: str = Path(..., description="معرّف الحقل لتسجيل قيد دفتره اليوميّ"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يُدِيم (upsert) قيد دفتر مياه يوميّاً للحقل (معزول بالمستأجِر، RLS).

    يتحقّق أوّلاً أنّ الحقل يخصّ المستأجِر (404 وإلّا)، ثمّ يُدرِج/يُحدِّث القيد في
    ``water_ledger`` (v98). idempotent عبر ``ON CONFLICT (field_id, ledger_date)
    DO UPDATE`` (إعادة الإرسال تُحدِّث لا تُكرّر). صدق: القاعدة غير مفعّلة
    (``DATABASE_URL``) ⇒ 503 موثَّق (لا ادّعاء حفظ)؛ مدخل غير صالح ⇒ 422؛ لا اختراع
    أرقام — الناقص يُحفَظ NULL.
    """
    try:
        norm = normalize_ledger_input(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"مدخل دفتر غير صالح: {e}") from e
    if _DB_POOL is None:
        raise HTTPException(
            status_code=503,
            detail="تعذّر حفظ قيد الدفتر (القاعدة غير مفعّلة DATABASE_URL أو الهجرات غير مطبّقة).",
        )
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            await conn.execute(
                "INSERT INTO water_ledger "
                "(tenant_id, field_id, ledger_date, et0_mm, kc, etc_mm, rain_mm, "
                " irrigation_mm, soil_moisture_pct, depletion_mm, deficit_mm, "
                " stage, decision, confidence, created_by, created_at, updated_at) "
                "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, "
                " $13, $14, $15, now(), now()) "
                "ON CONFLICT (field_id, ledger_date) DO UPDATE SET "
                " et0_mm = EXCLUDED.et0_mm, kc = EXCLUDED.kc, etc_mm = EXCLUDED.etc_mm, "
                " rain_mm = EXCLUDED.rain_mm, irrigation_mm = EXCLUDED.irrigation_mm, "
                " soil_moisture_pct = EXCLUDED.soil_moisture_pct, "
                " depletion_mm = EXCLUDED.depletion_mm, deficit_mm = EXCLUDED.deficit_mm, "
                " stage = EXCLUDED.stage, decision = EXCLUDED.decision, "
                " confidence = EXCLUDED.confidence, updated_at = now()",
                str(user.tenant_id),
                field_id,
                norm["ledger_date"],
                norm["et0_mm"],
                norm["kc"],
                norm["etc_mm"],
                norm["rain_mm"],
                norm["irrigation_mm"],
                norm["soil_moisture_pct"],
                norm["depletion_mm"],
                norm["deficit_mm"],
                norm["stage"],
                norm["decision"],
                norm["confidence"],
                user.user_id,
            )
    except HTTPException:
        raise  # 404 (حقل خارج المستأجِر) يصعد كما هو
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق (لا ادّعاء حفظ)
        raise _db_unavailable("حفظ قيد الدفتر", e) from e
    return {
        "field_id": field_id,
        "ledger_date": norm["ledger_date"].isoformat(),
        "persisted": True,
    }


@router.get("/api/v1/fields/{field_id}/water-ledger")
async def list_water_ledger(
    field_id: str = Path(..., description="معرّف الحقل لجلب دفتره اليوميّ"),
    date_from: str | None = Query(None, alias="from", description="من تاريخ (YYYY-MM-DD)"),
    date_to: str | None = Query(None, alias="to", description="إلى تاريخ (YYYY-MM-DD)"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """دفتر مياه الحقل اليوميّ (مرتَّب بالتاريخ تصاعديّاً) — معزول بالمستأجِر (RLS).

    يتحقّق أوّلاً أنّ الحقل يخصّ المستأجِر (404 وإلّا)، ثمّ يُرجِع ``{field_id, entries,
    total}``. مدى التاريخ اختياريّ (``from``/``to``، YYYY-MM-DD). صدق: القاعدة غير
    مفعّلة (``DATABASE_URL``) ⇒ قائمة فارغة + سبب (لا قيود مخترَعة)؛ تعذّر القاعدة
    أثناء التنفيذ ⇒ 503 موثَّق؛ تاريخ غير صالح ⇒ 422.
    """
    try:
        d_from = parse_ledger_date(date_from) if date_from else None
        d_to = parse_ledger_date(date_to) if date_to else None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"مدى تاريخ غير صالح: {e}") from e
    if _DB_POOL is None:
        return {
            "field_id": field_id,
            "entries": [],
            "total": 0,
            "note_ar": "القاعدة غير مفعّلة (DATABASE_URL) — لا دفتر مُخزَّن",
        }
    # بناء WHERE بارامتريّ تدريجيّاً (لا حقن): field_id إلزاميّ + مدى اختياريّ.
    clauses = ["field_id = $1"]
    args: list = [field_id]
    if d_from is not None:
        args.append(d_from)
        clauses.append(f"ledger_date >= ${len(args)}")
    if d_to is not None:
        args.append(d_to)
        clauses.append(f"ledger_date <= ${len(args)}")
    where_sql = " AND ".join(clauses)
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            rows = await conn.fetch(
                f"SELECT {LEDGER_SELECT_COLS} FROM water_ledger "
                f"WHERE {where_sql} ORDER BY ledger_date ASC",
                *args,
            )
    except HTTPException:
        raise  # 404 (حقل خارج المستأجِر) يصعد كما هو
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق (لا اختراع قيود)
        raise _db_unavailable("جلب الدفتر", e) from e
    entries = [row_to_ledger_entry(r) for r in rows]
    return {"field_id": field_id, "entries": entries, "total": len(entries)}
