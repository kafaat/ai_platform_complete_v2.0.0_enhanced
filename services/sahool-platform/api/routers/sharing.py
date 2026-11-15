"""Persisted, tenant-scoped sharing credentials and revocation.

The legacy POST /api/v1/sharing/generate-key response never persisted its token;
it has been superseded by POST /api/v1/sharing/keys. Removing that phantom
credential endpoint funds the revocation route inside the route-budget ratchet.
Both operations require the owner's invitation permission and tenant RLS.
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    SharingKeyCreateRequest,
    UserSchema,
    get_current_user,
    get_pool,
    require_permission,
    tenant_connection,
)
from api.sharing import (
    SharingKeyService,
    SharingScope as _SScope,
    ThirdPartyType as _TPType,
)

router = APIRouter()


@router.post("/api/v1/sharing/keys")
async def create_sharing_key(
    req: SharingKeyCreateRequest,
    user: UserSchema = Depends(require_permission(Permission.USER_INVITE)),
):
    """ينشئ ويحفظ مفتاح مشاركة (عبر tenant_connection — RLS مُطبَّق)."""
    try:
        scope = _SScope(req.scope)
        tp = _TPType(req.third_party_type) if req.third_party_type else None
        async with tenant_connection(user) as conn:
            svc = SharingKeyService(get_pool(), conn=conn)
            key = await svc.create_key(
                tenant_id=user.tenant_id,
                created_by=user.user_id,
                scope=scope,
                valid_days=req.valid_days,
                third_party_name=req.third_party_name,
                third_party_type=tp,
                allowed_field_ids=req.allowed_field_ids,
            )
        return {
            "key_id": key.key_id,
            "key_plaintext": key.key_plaintext,  # مرّة واحدة
            "key_prefix": key.key_prefix,
            "scope": key.scope.value,
            "third_party_type": tp.value if tp else None,
            "expires_at": key.expires_at,
            "note_ar": "مفتاح مشاركة محفوظ وقابل للإلغاء؛ احتفظ به الآن لأنه لن يُعرض مجدداً.",
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/api/v1/sharing/keys")
async def list_sharing_keys(
    include_revoked: bool = False,
    user: UserSchema = Depends(get_current_user),
):
    """يسرد مفاتيح المشاركة للمستأجر (عبر tenant_connection — RLS مُطبَّق)."""
    async with tenant_connection(user) as conn:
        svc = SharingKeyService(get_pool(), conn=conn)
        keys = await svc.list_keys(user.tenant_id, include_revoked=include_revoked)
    return {"keys": keys}


@router.post("/api/v1/sharing/keys/{key_id}/revoke")
async def revoke_sharing_key(
    key_id: str,
    user: UserSchema = Depends(require_permission(Permission.USER_INVITE)),
):
    """Revoke a persisted sharing credential under the owner's RLS scope.

    This path does not treat /generate-key output as a persisted credential.
    A missing or foreign key receives the same 404 without disclosing its owner.
    """
    try:
        key_id = str(_uuid.UUID(key_id))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="invalid_sharing_key_id") from exc
    try:
        async with tenant_connection(user) as conn:
            svc = SharingKeyService(get_pool(), conn=conn)
            revoked = await svc.revoke_key(key_id, str(user.tenant_id))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        from api.main import _db_unavailable

        raise _db_unavailable("إلغاء مفتاح مشاركة", exc) from exc
    if not revoked:
        raise HTTPException(status_code=404, detail="sharing_key_not_found")
    return {"key_id": key_id, "status": "revoked"}
