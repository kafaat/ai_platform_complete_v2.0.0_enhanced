"""api/routers/security_audit.py — سجلّ تدقيق الرفض الأمنيّ (cross-tenant / authz).

نقطة إدارة (AUDIT_VIEW) تعرض أحدث حالات رفض مستأجِر المُنادي: وصول خارج النطاق أو صلاحية
غير كافية أو فشل مصادقة. المصدر ``audit_log`` الدائم (core.tenant_audit.DenialStore) حين
تتوفّر القاعدة، وإلّا الحلقة في-الذاكرة؛ الحقل ``source`` (db | memory) يقول أيّهما.
"""

from __future__ import annotations

from core.tenant_audit import AUDIT, DENIAL_STORE
from fastapi import APIRouter, Depends, Query

from api.main import Permission, UserSchema, require_permission, tenant_connection

router = APIRouter()


@router.get("/api/v1/admin/security/denials")
async def security_denials(
    limit: int | None = Query(default=None, ge=1, le=200),
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """أحدث حالات الرفض الأمنيّ + ملخّص (إجماليّ/لكلّ نوع/آخر وقت)، لمستأجِر المُنادي فقط."""
    tenant_id = str(user.tenant_id)
    durable = await DENIAL_STORE.read_durable(
        lambda: tenant_connection(user), tenant_id, limit, capacity=AUDIT.maxlen
    )
    if durable is not None:
        denials, summary = durable
        return {"denials": denials, "summary": summary, "source": "db"}
    return {
        "denials": AUDIT.recent(limit=limit, tenant_id=tenant_id),
        "summary": AUDIT.summary(tenant_id=tenant_id),
        "source": "memory",
    }
