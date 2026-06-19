"""api/routers/kc_timeseries.py — تخزين Kc الدائم (crop_kc_timeseries) عبر HTTP.

غلافٌ رفيع بقاعدة (مخطّط v76): يحفظ Kc المُشتقّ (upsert) ويقرأ سلسلته التاريخيّة
ويقارن موسمين — فيصبح Kc قابلاً للمقارنة عبر المواسم بدل إعادة حسابه بلا أثر.

الكتابة/القراءة عبر `tenant_connection` (RLS مفعّل بـcurrent_setting) — عزل المستأجِر
مضمون، و`tenant_id` من المستخدم المُصادَق. بناء الصفّ ومنطق المقارنة نقيّان في
`core.kc_persistence`. لا منطق هنا غير التحويل + I/O القاعدة.

النقاط:
  • POST /api/v1/agro/kc-timeseries                    — حفظ/تحديث Kc موسم (upsert)
  • GET  /api/v1/agro/kc-timeseries/{field_id}         — السلسلة التاريخيّة لحقل
  • GET  /api/v1/agro/kc-timeseries/{field_id}/compare — مقارنة موسمين
"""

from __future__ import annotations

from core.kc_extraction_engine import FaoStageKc
from core.kc_persistence import build_kc_record, compare_kc_rows
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()


class KcPersistRequest(BaseModel):
    """Kc موسم مُشتقّ للحفظ — قيم المراحل اختياريّة (None = ناقص، لا يُختلق)."""

    field_id: str
    crop_id: str
    season_id: str
    scenario_type: str = "potential"
    cfet: float = 1.0
    kc_ini: float | None = None
    kc_mid: float | None = None
    kc_end: float | None = None
    kcb_ini: float | None = None
    kcb_mid: float | None = None
    kcb_end: float | None = None


_UPSERT = (
    "INSERT INTO crop_kc_timeseries (tenant_id, field_id, crop_id, season_id, "
    "scenario_type, kc_ini, kc_mid, kc_end, kcb_ini, kcb_mid, kcb_end, cfet, source) "
    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) "
    "ON CONFLICT (tenant_id, field_id, crop_id, season_id, scenario_type) "
    "DO UPDATE SET kc_ini=EXCLUDED.kc_ini, kc_mid=EXCLUDED.kc_mid, kc_end=EXCLUDED.kc_end, "
    "kcb_ini=EXCLUDED.kcb_ini, kcb_mid=EXCLUDED.kcb_mid, kcb_end=EXCLUDED.kcb_end, "
    "cfet=EXCLUDED.cfet, source=EXCLUDED.source, updated_at=NOW() "
    "RETURNING kc_id, season_id, scenario_type"
)

_SELECT = (
    "SELECT field_id, crop_id, season_id, scenario_type, kc_ini, kc_mid, kc_end, "
    "kcb_ini, kcb_mid, kcb_end, cfet, source, created_at, updated_at "
    "FROM crop_kc_timeseries WHERE field_id = $1 "
    "AND ($2::text IS NULL OR crop_id = $2) "
    "AND ($3::text IS NULL OR scenario_type = $3) "
    "ORDER BY season_id"
)

_SELECT_ONE = (
    "SELECT crop_id, season_id, kc_ini, kc_mid, kc_end "
    "FROM crop_kc_timeseries "
    "WHERE field_id = $1 AND crop_id = $2 AND season_id = $3 AND scenario_type = $4"
)


def _row_to_dict(row) -> dict:
    """يحوّل صفّ asyncpg إلى dict قابل لتسلسل JSON (الطوابع الزمنيّة ISO)."""
    d = dict(row)
    for key in ("created_at", "updated_at"):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    return d


@router.post("/api/v1/agro/kc-timeseries")
async def persist_kc(
    req: KcPersistRequest,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
):
    """يحفظ (أو يحدّث upsert) Kc المُشتقّ لموسم. السيناريو غير الصالح ⇒ 422."""
    try:
        rec = build_kc_record(  # نقيّ: يتحقّق من السيناريو ويبني الصفّ
            FaoStageKc(
                kc_ini=req.kc_ini,
                kc_mid=req.kc_mid,
                kc_end=req.kc_end,
                kcb_ini=req.kcb_ini,
                kcb_mid=req.kcb_mid,
                kcb_end=req.kcb_end,
            ),
            field_id=req.field_id,
            tenant_id=str(user.tenant_id),
            crop_id=req.crop_id,
            season_id=req.season_id,
            scenario_type=req.scenario_type,
            cfet=req.cfet,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                _UPSERT,
                rec["tenant_id"],
                rec["field_id"],
                rec["crop_id"],
                rec["season_id"],
                rec["scenario_type"],
                rec["kc_ini"],
                rec["kc_mid"],
                rec["kc_end"],
                rec["kcb_ini"],
                rec["kcb_mid"],
                rec["kcb_end"],
                rec["cfet"],
                rec["source"],
            )
        return {
            "kc_id": str(row["kc_id"]),
            "season_id": row["season_id"],
            "scenario_type": row["scenario_type"],
            "stored": True,
        }
    except Exception as e:  # noqa: BLE001 — يُترجَم إلى 503 موحّد
        raise _db_unavailable("حفظ Kc", e) from e


@router.get("/api/v1/agro/kc-timeseries/{field_id}")
async def list_kc(
    field_id: str,
    crop_id: str | None = Query(None),
    scenario_type: str | None = Query(None),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يُرجِع سلسلة Kc التاريخيّة لحقل (مُرشّحة بـRLS)، مرتّبة بالموسم."""
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(_SELECT, field_id, crop_id, scenario_type)
        return {"field_id": field_id, "count": len(rows), "series": [_row_to_dict(r) for r in rows]}
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة سلسلة Kc", e) from e


@router.get("/api/v1/agro/kc-timeseries/{field_id}/compare")
async def compare_kc(
    field_id: str,
    crop_id: str = Query(...),
    current_season: str = Query(...),
    previous_season: str = Query(...),
    scenario_type: str = Query("potential"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يقارن Kc موسمين لنفس الحقل/المحصول (اتّجاه كلّ مرحلة + حُكم عربيّ). 404 إن غاب موسم."""
    try:
        async with tenant_connection(user) as conn:
            cur = await conn.fetchrow(_SELECT_ONE, field_id, crop_id, current_season, scenario_type)
            prev = await conn.fetchrow(
                _SELECT_ONE, field_id, crop_id, previous_season, scenario_type
            )
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("مقارنة Kc", e) from e
    if cur is None or prev is None:
        missing = current_season if cur is None else previous_season
        raise HTTPException(status_code=404, detail=f"لا سجلّ Kc للموسم: {missing}")
    return compare_kc_rows(dict(cur), dict(prev))
