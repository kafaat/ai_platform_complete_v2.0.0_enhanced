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
    idempotent عبر ``ON CONFLICT (field_id, ledger_date) DO UPDATE``، جزئيّ: لا يُكتَب
    عند التعارض إلّا ما أُرسِل (W0-13).
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

from api import main as api_main
from api.main import (
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.water_efficiency import compute_water_efficiency
from api.water_ledger_auto import AUTO_CREATED_BY
from api.water_ledger_compute import (
    LEDGER_SELECT_COLS,
    LEDGER_UPSERT_SQL,
    is_irrigation_report,
    ledger_write_columns,
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
    DO UPDATE`` (إعادة الإرسال تُحدِّث لا تُكرّر). **جزئيّ (W0-13):** عند التعارض لا
    يُكتَب إلّا ما أرسله المستدعي؛ العمود الغائب يبقى كما هو. وبلاغ ريٍّ وحده
    (``{ledger_date, irrigation_mm}``) على يومٍ يحسبه العامل يُغيِّر الماء المضاف فقط،
    ويعيد العامل حساب الميزان حوله. صدق: القاعدة غير مفعّلة (``DATABASE_URL``) ⇒ 503
    موثَّق (لا ادّعاء حفظ)؛ مدخل غير صالح أو بلا عمود واحد ⇒ 422؛ لا اختراع أرقام —
    الناقص في قيدٍ جديد يُحفَظ NULL.
    """
    try:
        norm = normalize_ledger_input(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"مدخل دفتر غير صالح: {e}") from e
    columns = ledger_write_columns(req.model_fields_set)
    if not columns:
        # An empty write used to insert a person-owned row of NULLs that also blocked the worker.
        raise HTTPException(status_code=422, detail="مدخل دفتر غير صالح: لا عمود للكتابة")
    report = is_irrigation_report(columns)
    if report and norm["irrigation_mm"] is None:
        raise HTTPException(status_code=422, detail="مدخل دفتر غير صالح: irrigation_mm فارغ")
    if api_main._DB_POOL is None:
        raise HTTPException(
            status_code=503,
            detail="تعذّر حفظ قيد الدفتر (القاعدة غير مفعّلة DATABASE_URL أو الهجرات غير مطبّقة).",
        )
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            await conn.execute(
                LEDGER_UPSERT_SQL,
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
                # A report opens a day the worker owns; any other write is its author's day.
                AUTO_CREATED_BY if report else user.user_id,
                user.user_id if report else None,
                list(columns),
                AUTO_CREATED_BY,
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
    if api_main._DB_POOL is None:
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


@router.get("/api/v1/fields/{field_id}/water-efficiency")
async def field_water_efficiency(
    field_id: str = Path(..., description="معرّف الحقل لحساب كفاءة مياهه على فترة"),
    date_from: str | None = Query(None, alias="from", description="من تاريخ (YYYY-MM-DD)"),
    date_to: str | None = Query(None, alias="to", description="إلى تاريخ (YYYY-MM-DD)"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """كفاءة استخدام المياه للحقل على فترة (Outcome KPI) — تجميع من دفتر المياه (RLS).

    يُجمّع ETc (الطلب) مقابل الماء المُورَّد (ريّ + مطر فعّال) من قيود الدفتر فيُخرِج
    `water_use_efficiency`/`demand_met_pct`/`over_application_mm` — يخدم «خفض المياه».
    صدق: الـWUE القائم على الغلّة خارج النطاق (لا حلقة غلّة)؛ لا طلب/لا ريّ مُسجَّل ⇒
    `status=needs_data`/`needs_irrigation_data` (لا رقم مُضلِّل). القاعدة غير مفعّلة ⇒
    كتلة `needs_data` (نظير قائمة الدفتر الفارغة)؛ تعذّر القاعدة ⇒ 503؛ تاريخ فاسد ⇒ 422.
    """
    try:
        d_from = parse_ledger_date(date_from) if date_from else None
        d_to = parse_ledger_date(date_to) if date_to else None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"مدى تاريخ غير صالح: {e}") from e
    if api_main._DB_POOL is None:
        return {
            "field_id": field_id,
            "period": {"from": date_from, "to": date_to},
            "efficiency": compute_water_efficiency([]),  # كتلة needs_data صادقة
            "note_ar": "القاعدة غير مفعّلة (DATABASE_URL) — لا دفتر لحساب الكفاءة",
        }
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
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق (لا اختراع كفاءة)
        raise _db_unavailable("حساب كفاءة المياه", e) from e
    entries = [row_to_ledger_entry(r) for r in rows]
    return {
        "field_id": field_id,
        "period": {"from": date_from, "to": date_to},
        "efficiency": compute_water_efficiency(entries),
    }
