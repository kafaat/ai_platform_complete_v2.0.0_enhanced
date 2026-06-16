"""api/routers/security_audit.py — سجلّ تدقيق الرفض الأمنيّ (cross-tenant / authz).

نقطة إدارة تعرض أحدث حالات الرفض المُسجَّلة في core.tenant_audit: محاولات وصول خارج
نطاق المستأجِر (RLS) أو صلاحية غير كافية أو فشل مصادقة. مُقيَّدة بصلاحيّة التدقيق
(AUDIT_VIEW). معرفة في-الذاكرة (لا قاعدة) — للمراقبة التشغيليّة.
"""

from __future__ import annotations

from core.tenant_audit import AUDIT
from fastapi import APIRouter, Depends, Query

from api.main import Permission, UserSchema, require_permission

router = APIRouter()


@router.get("/api/v1/admin/security/denials")
async def security_denials(
    limit: int | None = Query(default=None, ge=1, le=200),
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """أحدث حالات الرفض الأمنيّ + ملخّص (إجماليّ/لكلّ نوع/آخر وقت)."""
    return {"denials": AUDIT.recent(limit=limit), "summary": AUDIT.summary()}
