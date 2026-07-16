"""api/routers/prescriptions.py — وصفات المعدّل المتغيّر اليدويّة (Manual VRT)
==============================================================================
نظير FieldView "manual prescriptions" — وصفة **يدويّة** صرفة: المستخدِم يرسم مناطق
الإدارة (zones) على خريطة الحقل ويضبط لكلّ منطقة معدّلاً + وحدة، ثمّ يسمّيها ويختار
نوع المنتج {seed|fertility} ويحفظها.

صدق منهجيّ (مهمّ): هذا **ليس** توليداً agronomic آليّاً. الـGenerators القائمة
(``api/prescriptions.py`` بقواعد crop/lab، و``core/vrt_manual_maps.py``) تبقى في
الذاكرة (لا إدامة هنا)، و``useFieldPrescription`` في الواجهة قراءةُ تقطيع كمّيّ
(quantile) من الراستر — ليست وصفةً محفوظة. هذا الموجِّه يُديم وصفةً يدويّة قابلة
للقراءة فقط؛ لا اختراع مناطق/معدّلات.

النقاط (v95، جدول ``prescriptions`` معزول بالمستأجِر، RLS):
  • POST /api/v1/fields/{field_id}/prescriptions — حفظ وصفة (FIELD_EDIT).
  • GET  /api/v1/fields/{field_id}/prescriptions — سرد الوصفات (FIELD_VIEW، الأحدث أوّلاً).

التصدير (GeoJSON/CSV) يتمّ في الواجهة (Blob/URL، بلا اعتماديّة). صيغ المُتحكِّمات
(ISOXML/Shapefile) **مؤجّلة كـTODO موثَّق** — لا ندّعي إنتاج ما لا ننتجه فعلاً.

نمط الاستيراد من ``api.main`` يطابق ``routers/scouting.py`` (نمط P0): التبعيّات
(``get_current_user``/``UserSchema``/RLS) تبقى في ``main`` ويستوردها هذا الموجِّه؛
و``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد تعريف كلّ التبعيات) فيُحلّ
الاستيراد الدائريّ. SQL بارامتريّ بالكامل (لا حقن).
"""

from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
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
from api.prescription_shapefile import build_shapefile_zip

logger = logging.getLogger(__name__)

router = APIRouter()

# أنواع المنتج المسموحة (يدويّ صرف — لا يتجاوز ما تنتجه الواجهة فعلاً).
_PRODUCT_TYPES = {"seed", "fertility"}

# أعمدة القراءة لجدول prescriptions (v95) — مطابقة لمخرَج الحفظ.
_RX_SELECT_COLS = "prescription_id, field_id, season_id, season_resolution_status, name, product_type, zones, created_by, created_at"


# ─── النماذج ─────────────────────────────────────────────────────


class PrescriptionZone(BaseModel):
    """منطقة إدارة واحدة: هندسة GeoJSON يرسمها المستخدِم + معدّل + وحدة."""

    geometry: dict  # GeoJSON Polygon (يرسمه المستخدِم في الواجهة)
    rate: float  # المعدّل (seeds/m² أو kg/ha) — يضبطه المستخدِم
    unit: str  # الوحدة (مثل "seeds/m2" أو "kg/ha")


class PrescriptionCreateRequest(BaseModel):
    """طلب حفظ وصفة يدويّة. ``prescription_id`` معرّف العميل (idempotency)."""

    prescription_id: str = Field(..., min_length=1, max_length=128)
    season_id: str | None = Field(default=None, min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=200)
    product_type: str = Field(default="seed")
    zones: list[PrescriptionZone] = Field(default_factory=list)


def _row_to_prescription(row) -> dict:
    """يحوّل صفّ prescriptions إلى dict (مفتاح prescription_id).

    نقيّ (لا I/O) ليُختبَر بـunit بلا قاعدة حيّة. ``zones`` JSONB قد يعود نصّاً
    (asyncpg) فيُفكَّك؛ إن كان قائمةً أصلاً (mock) يُمرَّر كما هو. ``created_at``
    (timestamptz) يُنسَّق ISO؛ نصّاً أصلاً (mock) يُمرَّر كما هو.
    """
    zones = row["zones"]
    if isinstance(zones, str):
        try:
            zones = json.loads(zones)
        except (ValueError, TypeError):
            zones = []
    created = row["created_at"]
    created_iso = created.isoformat() if hasattr(created, "isoformat") else (created or "")
    return {
        "prescription_id": row["prescription_id"],
        "field_id": row["field_id"],
        "season_id": row.get("season_id") if hasattr(row, "get") else row["season_id"],
        "season_resolution_status": (
            row.get("season_resolution_status")
            if hasattr(row, "get")
            else row["season_resolution_status"]
        ),
        "name": row["name"],
        "product_type": row["product_type"],
        "zones": zones if isinstance(zones, list) else [],
        "created_by": row["created_by"],
        "created_at": created_iso,
    }


@router.post("/api/v1/fields/{field_id}/prescriptions")
async def create_prescription(
    req: PrescriptionCreateRequest,
    field_id: str = Path(..., description="معرّف الحقل لحفظ وصفته"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    """يحفظ وصفة معدّل متغيّر **يدويّة** للحقل (معزولة بالمستأجِر، RLS).

    يتحقّق أوّلاً أنّ الحقل يخصّ المستأجِر (404 وإلّا)، ثمّ يُدرِج الوصفة في
    ``prescriptions`` (v95). idempotent عبر ``ON CONFLICT (prescription_id) DO NOTHING``
    (إعادة الإرسال لا تُكرّر). يُرجِع الوصفة المحفوظة. صدق: القاعدة غير مفعّلة
    (``DATABASE_URL``) ⇒ 503 موثَّق (لا ادّعاء حفظ)؛ نوع منتج غير مدعوم ⇒ 422.
    """
    season_mode = os.getenv("FII_PRESCRIPTION_SEASON_MODE", "audit").strip().lower()
    if season_mode not in {"audit", "enforce"}:
        season_mode = "audit"
    if not req.season_id and season_mode == "enforce":
        raise HTTPException(status_code=422, detail={"code": "SEASON_CONTEXT_REQUIRED"})
    if not req.season_id:
        logger.warning(
            "fii prescription missing season context field_id=%s mode=%s", field_id, season_mode
        )
    if req.product_type not in _PRODUCT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"نوع المنتج غير مدعوم (المسموح: {sorted(_PRODUCT_TYPES)})",
        )
    if _DB_POOL is None:
        raise HTTPException(
            status_code=503,
            detail="تعذّر حفظ الوصفة (القاعدة غير مفعّلة DATABASE_URL أو الهجرات غير مطبّقة).",
        )
    zones_payload = [z.model_dump() for z in req.zones]
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            await conn.execute(
                "INSERT INTO prescriptions "
                "(prescription_id, tenant_id, field_id, season_id, season_resolution_status, name, product_type, "
                " zones, created_by, created_at) "
                "VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8::jsonb, $9, now()) "
                "ON CONFLICT (prescription_id) DO NOTHING",
                req.prescription_id,
                str(user.tenant_id),
                field_id,
                req.season_id,
                "resolved" if req.season_id else "unresolved",
                req.name,
                req.product_type,
                json.dumps(zones_payload),
                user.user_id,
            )
    except HTTPException:
        raise  # 404 (حقل خارج المستأجِر) يصعد كما هو
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق (لا ادّعاء حفظ)
        raise _db_unavailable("حفظ الوصفة", e) from e
    return {
        "prescription_id": req.prescription_id,
        "field_id": field_id,
        "season_id": req.season_id,
        "season_resolution_status": "resolved" if req.season_id else "unresolved",
        "name": req.name,
        "product_type": req.product_type,
        "zones": zones_payload,
        "created_by": user.user_id,
        "persisted": True,
    }


@router.get("/api/v1/fields/{field_id}/prescriptions")
async def list_prescriptions(
    field_id: str = Path(..., description="معرّف الحقل لجلب وصفاته"),
    include_legacy: bool = Query(
        False, description="إظهار السجلات القديمة غير المحسومة للإدارة فقط"
    ),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """وصفات الحقل المحفوظة (الأحدث أوّلاً) — معزولة بالمستأجِر (RLS).

    تتحقّق أوّلاً أنّ الحقل يخصّ المستأجِر (404 وإلّا)، ثمّ تُرجِع
    ``{field_id, prescriptions, total}``. صدق: القاعدة غير مفعّلة (``DATABASE_URL``)
    ⇒ قائمة فارغة + سبب (لا وصفات مخترَعة)؛ تعذّر القاعدة أثناء التنفيذ ⇒ 503 موثَّق.
    """
    if _DB_POOL is None:
        return {
            "field_id": field_id,
            "prescriptions": [],
            "total": 0,
            "note_ar": "القاعدة غير مفعّلة (DATABASE_URL) — لا وصفات مُخزَّنة",
        }
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            rows = await conn.fetch(
                f"SELECT {_RX_SELECT_COLS} FROM prescriptions "
                "WHERE field_id = $1 "
                "AND ($2::boolean OR season_resolution_status <> 'unresolved') "
                "ORDER BY created_at DESC",
                field_id,
                # Audit-mode (default) shows legacy 'unresolved' rows so v193 does not
                # silently hide existing prescriptions; only enforce mode hides them
                # unless include_legacy is explicitly requested.
                include_legacy
                or os.getenv("FII_PRESCRIPTION_SEASON_MODE", "audit").strip().lower() != "enforce",
            )
    except HTTPException:
        raise  # 404 (حقل خارج المستأجِر) يصعد كما هو
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق (لا اختراع وصفات)
        raise _db_unavailable("جلب الوصفات", e) from e
    items = [_row_to_prescription(r) for r in rows]
    return {"field_id": field_id, "prescriptions": items, "total": len(items)}


@router.get("/api/v1/fields/{field_id}/prescriptions/{prescription_id}/export")
async def export_prescription(
    field_id: str = Path(..., description="معرّف الحقل"),
    prescription_id: str = Path(..., description="معرّف الوصفة"),
    fmt: str = Query("shapefile", alias="format", description="الصيغة (المتاح: shapefile)"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يصدّر الوصفة كـ**Shapefile** (ZIP: .shp/.shx/.dbf/.prj) للمُتحكِّمات الزراعيّة (اقتباس CultiWise).

    صدق: Shapefile فقط هنا (GeoJSON/CSV يُنتَجان في الواجهة؛ **ISOXML مؤجَّل كـTODO موثَّق** — لا
    يُنتَج بعد ⇒ 422). معزول بالمستأجِر (RLS)؛ حقل/وصفة خارج المستأجِر ⇒ 404؛ القاعدة معطّلة ⇒ 503.
    """
    if fmt != "shapefile":
        raise HTTPException(
            status_code=422,
            detail="صيغة غير مدعومة (المتاح: shapefile؛ ISOXML قيد التطوير — TODO موثَّق)",
        )
    if _DB_POOL is None:
        raise HTTPException(status_code=503, detail="القاعدة غير مفعّلة (DATABASE_URL)")
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            row = await conn.fetchrow(
                f"SELECT {_RX_SELECT_COLS} FROM prescriptions "
                "WHERE prescription_id = $1 AND field_id = $2",
                prescription_id,
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تصدير الوصفة", e) from e
    if row is None:
        raise HTTPException(status_code=404, detail="الوصفة غير موجودة")
    status = (
        row.get("season_resolution_status")
        if hasattr(row, "get")
        else row["season_resolution_status"]
    )
    if status == "unresolved":
        # Audit-only by default (Increment 4): freezing legacy rows from export is an
        # ENFORCE-mode behaviour. In audit mode we log and allow, so applying v193
        # (which defaults every legacy row to 'unresolved') does NOT retroactively
        # freeze existing prescriptions. Flip to enforce only after legacy rows are
        # triaged/backfilled.
        _season_mode = os.getenv("FII_PRESCRIPTION_SEASON_MODE", "audit").strip().lower()
        if _season_mode == "enforce":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "LEGACY_SEASON_UNRESOLVED",
                    "message": "الوصفة القديمة غير المحسومة مجمّدة ولا يمكن تصديرها للتنفيذ",
                },
            )
        logger.warning(
            "fii prescription export of unresolved legacy row (audit mode, allowed) prescription_id=%s",
            row["prescription_id"] if hasattr(row, "__getitem__") else "?",
        )
    rx = _row_to_prescription(row)
    try:
        data = build_shapefile_zip(rx["name"], rx["product_type"], rx["zones"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"تعذّر بناء Shapefile: {e}") from e
    except ImportError:  # pragma: no cover — مكتبة pyshp غير مُثبَّتة في هذه البيئة
        raise HTTPException(status_code=503, detail="مكتبة تصدير Shapefile غير متاحة") from None
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="prescription.zip"'},
    )
