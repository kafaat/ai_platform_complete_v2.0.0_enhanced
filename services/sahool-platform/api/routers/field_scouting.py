"""api/routers/field_scouting.py — مسارات الاستطلاع/الدبابيس وخطّة المشي للحقل.

شريحة مُستخرَجة من ``api/routers/fields.py`` (تفكيك تدريجيّ محفوظ-السلوك للملفّ الأكبر):
نُقلت معالِجات الاستطلاع/الدبابيس وخطّة المشي حرفيّاً — بنفس المسارات/الطلبات/المخرجات/
الأذونات/مخطّط OpenAPI — دون أيّ تغيير في السلوك:

  • ``POST /api/v1/fields/{field_id}/pins``          → ``create_pin``
  • ``POST /api/v1/fields/{field_id}/walk-plan``     → ``field_walk_plan``
  • ``POST /api/v1/fields/{field_id}/walk-plan/pdf`` → ``field_walk_plan_pdf``

ويُنقل معها مساعِدها المخصّص ``_persist_scouting_pin`` (مستهلِكه الوحيد ``create_pin``).

التسجيل تلقائيّ عبر ``api.router_registry.register_routers`` (حلقة ``pkgutil`` على
``api/routers/`` — أيّ وحدة تُصدّر ``router`` تُضمّ). بما أنّ المسارات نُقلت (لا نُسخت)
من ``fields.py`` فلا تكرار (مسار، طريقة).

الاعتماديّات: الرموز المشتركة تُستورَد من مصادرها الأصليّة نفسها كما في ``fields.py``
(``api.main`` للتبعيات/النماذج/المساعِدات، ``api.scouting_pins`` لـ``make_pin``،
``api.walk_plan_pdf`` لتوليد PDF). لتفادي الاستيراد الدائريّ: ``api.main`` يُستورَد هنا،
وحلقة التسجيل تُنفَّذ في نهاية ``main.py`` بعد اكتمال تعريف كلّ تلك الرموز.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from api.main import (
    _DB_POOL,
    PinCreateRequest,
    UserSchema,
    WalkPlanRequest,
    _build_walk_plan,
    get_current_user,
    tenant_connection,
)
from api.scouting_pins import make_pin
from api.walk_plan_pdf import walk_plan_to_pdf_bytes

router = APIRouter()


@router.post("/api/v1/fields/{field_id}/pins")
async def create_pin(
    field_id: str,
    req: PinCreateRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يتحقّق من مشاهدة ميدانيّة ثمّ يُديمها (RLS) ويُرجعها مُطبَّعة.

    سابقاً: تحقّق + إرجاع فقط (الحفظ كان على الموبايل offline-first) — فلا قراءة
    خادميّة. الآن يُثبَّت الدبّوس في ``scouting_pins`` (v94، معزول بالمستأجِر) ليُقرأ
    عبر ``GET /api/v1/scouting/pins?field_id=…`` (نظير FieldView). صدق: التحقّق هو
    مصدر الحقيقة؛ الإدامة best-effort — لو تعذّرت القاعدة يبقى الدبّوس صالحاً ويُعلَن
    ``persisted=false`` (لا اختراع نجاح، يبقى المسار offline-first سليماً). idempotent
    عبر ``ON CONFLICT (pin_id) DO NOTHING`` (إعادة المزامنة لا تُكرّر).
    """
    try:
        pin = make_pin(
            req.pin_id,
            field_id,
            req.lat,
            req.lng,
            req.issue_category,
            req.severity,
            req.status,
            req.persistence,
            crop=req.crop,
            issue_code=req.issue_code,
            note_ar=req.note_ar,
            photo_uri=req.photo_uri,
            color=req.color,
            created_by=req.created_by or user.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    out = pin.to_dict()
    persisted = await _persist_scouting_pin(user, pin)
    out["persisted"] = persisted
    return out


async def _persist_scouting_pin(user: UserSchema, pin) -> bool:
    """يُثبّت دبّوس مشاهدة في ``scouting_pins`` تحت سياق المستأجِر (RLS) — best-effort.

    يُرجِع ``True`` لو ثُبِّت (أو كان موجوداً مسبقاً idempotent)، و``False`` لو تعذّرت
    القاعدة (لا استثناء يصعد — المسار offline-first يبقى سليماً). SQL بارامتريّ
    بالكامل (لا حقن). ``created_at`` يُمرَّر كنصّ ISO من النواة ويُحوَّل بـ``::timestamptz``.
    """
    if _DB_POOL is None:
        return False
    try:
        async with tenant_connection(user) as conn:
            await conn.execute(
                "INSERT INTO scouting_pins "
                "(pin_id, tenant_id, field_id, lat, lng, issue_category, severity, "
                " status, persistence, crop, issue_code, note_ar, photo_uri, color, "
                " created_by, created_at) "
                "VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, "
                " $13, $14, $15, $16::timestamptz) "
                "ON CONFLICT (pin_id) DO NOTHING",
                pin.pin_id,
                str(user.tenant_id),
                pin.field_id,
                pin.lat,
                pin.lng,
                pin.issue_category.value,
                pin.severity.value,
                pin.status.value,
                pin.persistence.value,
                pin.crop,
                pin.issue_code,
                pin.note_ar,
                pin.photo_uri,
                pin.color,
                pin.created_by,
                pin.created_at or None,
            )
        return True
    except Exception:  # noqa: BLE001 — إدامة best-effort: تعذّر القاعدة ⇒ persisted=false
        logging.warning("scouting pin persistence failed for pin %s", pin.pin_id)
        return False


@router.post("/api/v1/fields/{field_id}/walk-plan")
def field_walk_plan(
    field_id: str,
    req: WalkPlanRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يحوّل وصفة الحقل إلى خطة مشي يدويّة قابلة للتنفيذ."""
    return _build_walk_plan(req).to_dict()


@router.post("/api/v1/fields/{field_id}/walk-plan/pdf")
def field_walk_plan_pdf(
    field_id: str,
    req: WalkPlanRequest,
    user: UserSchema = Depends(get_current_user),
):
    """نفس خطة المشي لكن كـPDF عربي للطباعة وأخذها للحقل."""
    plan = _build_walk_plan(req)
    try:
        pdf_bytes = walk_plan_to_pdf_bytes(plan.to_dict())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="walk_plan_{field_id}.pdf"'},
    )
