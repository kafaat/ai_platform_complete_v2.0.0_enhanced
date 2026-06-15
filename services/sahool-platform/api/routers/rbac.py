"""api/routers/rbac.py — حوكمة الصلاحيّات (RBAC Governance)
======================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.
لا تُمسّ منطق الصلاحيّات (الاستعلامات نقيّة فوق core.rbac_governance).

الاعتماديّات المشتركة (التبعيات/الأذونات) تبقى مُعرَّفة في ``api.main`` وتُستورَد
من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات. لتفادي
الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    UserSchema,
    require_permission,
)

router = APIRouter()


@router.get("/api/v1/rbac/who-can")
def rbac_who_can(
    permission: str,
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """الاستعلام العكسي: أيّ الأدوار تملك صلاحيّة معيّنة؟ (تدقيق أمني)."""
    from core.authorization import Permission as _P
    from core.rbac_governance import who_can

    try:
        perm = _P(permission)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"صلاحيّة غير معروفة: {permission}") from e
    return who_can(perm)


@router.get("/api/v1/rbac/permission-matrix")
def rbac_permission_matrix(
    user: UserSchema = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    """مصفوفة الصلاحيّات الكاملة (كلّ دور × كلّ صلاحيّة) — شفافيّة الحوكمة."""
    from core.rbac_governance import permission_matrix

    return permission_matrix()


@router.get("/api/v1/rbac/preview-role-change")
def rbac_preview_role_change(
    current_role: str,
    new_role: str,
    user: UserSchema = Depends(require_permission(Permission.USER_CHANGE_ROLE)),
):
    """معاينة أثر تغيير دور قبل تطبيقه (ما يُكتسَب/يُفقَد + تنبيه التصعيد)."""
    from core.rbac_governance import preview_role_change

    return preview_role_change(current_role, new_role)
