"""api/routers/master_data.py — البيانات المرجعيّة (Master Data)
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّتان حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات/مُصدِر الأحداث) تبقى مُعرَّفة في
``api.main`` وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات
الاختبارات. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته
فقط (بعد تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    UserSchema,
    _emit_domain_event,
    require_permission,
    tenant_connection,
)
from api.master_data_models import MasterDataRequest

router = APIRouter()


@router.post("/api/v1/master-data", status_code=201)
async def create_master_data(
    req: MasterDataRequest,
    user: UserSchema = Depends(require_permission(Permission.MASTER_DATA_MANAGE)),
):
    import json as _json
    import uuid as _uuid

    md_id = "md_" + _uuid.uuid4().hex[:12]
    async with tenant_connection(user) as conn:
        # نعتمد على قيد UNIQUE(tenant, category, code) لا SELECT-ثمّ-INSERT (سباق):
        # طلبان متزامنان قد يمرّان الفحص ثم يفشل الثاني — نلتقط unique_violation
        # (SQLSTATE 23505) ونُعيد 409 دائماً (لا 500). ملاحظة المراجعة.
        try:
            await conn.execute(
                """INSERT INTO master_data
                    (md_id, tenant_id, category, code, name_ar, name_en, metadata)
                   VALUES ($1, $2::uuid, $3, $4, $5, $6, $7::jsonb)""",
                md_id,
                str(user.tenant_id),
                req.category,
                req.code,
                req.name_ar,
                req.name_en,
                _json.dumps(req.metadata or {}),
            )
            await _emit_domain_event(
                conn,
                user,
                "MASTER_DATA_CREATED",
                "master_data",
                md_id,
                {"category": req.category, "code": req.code},
            )
        except Exception as e:  # noqa: BLE001 — نميّز unique_violation فقط
            if getattr(e, "sqlstate", None) == "23505":
                raise HTTPException(
                    status_code=409, detail="الرمز موجود مسبقاً في هذه الفئة"
                ) from None
            raise
    return {"md_id": md_id, "code": req.code, "message_ar": "أُضيف عنصر مرجعيّ"}


@router.get("/api/v1/master-data")
async def list_master_data(
    category: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.MASTER_DATA_VIEW)),
):
    """كتالوج البيانات المرجعيّة (مُرشَّح اختياريّاً بالفئة)."""
    async with tenant_connection(user) as conn:
        if category:
            rows = await conn.fetch(
                "SELECT md_id, category, code, name_ar, name_en, metadata, active "
                "FROM master_data WHERE category = $1 AND active ORDER BY name_ar",
                category,
            )
        else:
            rows = await conn.fetch(
                "SELECT md_id, category, code, name_ar, name_en, metadata, active "
                "FROM master_data WHERE active ORDER BY category, name_ar"
            )
    return [
        {
            "md_id": r["md_id"],
            "category": r["category"],
            "code": r["code"],
            "name_ar": r["name_ar"],
            "name_en": r["name_en"],
            "metadata": r["metadata"] if isinstance(r["metadata"], dict) else {},
        }
        for r in rows
    ]
