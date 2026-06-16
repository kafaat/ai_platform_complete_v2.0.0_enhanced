"""api/routers/documents.py — إدارة المستندات (Document Metadata)
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

⚠️ سجلّ بيانات وصفيّة فقط: لا يخزّن الملفّ الثنائيّ (blob).

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.document_models import DocumentRequest
from api.main import (
    Permission,
    UserSchema,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.post("/api/v1/documents", status_code=201)
async def register_document(
    req: DocumentRequest,
    user: UserSchema = Depends(require_permission(Permission.DOCUMENT_MANAGE)),
):
    """يسجّل بيانات مستند وصفيّة (لا blob — storage_ref يشير لتخزين الكائنات)."""
    import uuid as _uuid

    doc_id = "doc_" + _uuid.uuid4().hex[:12]
    async with tenant_connection(user) as conn:
        await conn.execute(
            """INSERT INTO documents
                (doc_id, tenant_id, category, field_id, title, storage_ref,
                 content_type, size_bytes, uploaded_by)
               VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9)""",
            doc_id,
            str(user.tenant_id),
            req.category,
            req.field_id,
            req.title,
            req.storage_ref,
            req.content_type,
            req.size_bytes,
            user.user_id,
        )
    return {"doc_id": doc_id, "title": req.title, "message_ar": "سُجّل المستند"}


@router.get("/api/v1/documents")
async def list_documents(
    category: str | None = None,
    field_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.DOCUMENT_VIEW)),
):
    """سجلّ المستندات (مُرشَّح اختياريّاً بالفئة و/أو الحقل) — معزول بالمستأجر."""
    clauses: list[str] = []
    params: list = []
    if category:
        params.append(category)
        clauses.append(f"category = ${len(params)}")
    if field_id:
        params.append(field_id)
        clauses.append(f"field_id = ${len(params)}")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            "SELECT doc_id, category, field_id, title, storage_ref, content_type, "
            "size_bytes, version, uploaded_by, created_at "
            f"FROM documents{where} ORDER BY created_at DESC",
            *params,
        )
    return [
        {
            "doc_id": r["doc_id"],
            "category": r["category"],
            "field_id": r["field_id"],
            "title": r["title"],
            "storage_ref": r["storage_ref"],
            "content_type": r["content_type"],
            "size_bytes": r["size_bytes"],
            "version": r["version"],
            "uploaded_by": r["uploaded_by"],
        }
        for r in rows
    ]


@router.get("/api/v1/documents/{doc_id}")
async def get_document(
    doc_id: str,
    user: UserSchema = Depends(require_permission(Permission.DOCUMENT_VIEW)),
):
    """بيانات مستند مفرد (404 إن غير موجود) — معزول بالمستأجر."""
    async with tenant_connection(user) as conn:
        r = await conn.fetchrow(
            "SELECT doc_id, category, field_id, title, storage_ref, content_type, "
            "size_bytes, version, uploaded_by, created_at "
            "FROM documents WHERE doc_id = $1",
            doc_id,
        )
    if r is None:
        raise HTTPException(status_code=404, detail="المستند غير موجود")
    return {
        "doc_id": r["doc_id"],
        "category": r["category"],
        "field_id": r["field_id"],
        "title": r["title"],
        "storage_ref": r["storage_ref"],
        "content_type": r["content_type"],
        "size_bytes": r["size_bytes"],
        "version": r["version"],
        "uploaded_by": r["uploaded_by"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }
