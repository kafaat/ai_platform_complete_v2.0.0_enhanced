"""api/routers/sharing.py — مفاتيح المشاركة (Sharing Keys)
========================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

النماذج والتبعيات المشتركة تبقى مُعرَّفة في ``api.main`` وتُستورَد من هنا. رموز
``api.sharing`` (SharingScope/ThirdPartyType/generate_key_plaintext/hash_key/
SharingKeyService) كانت مُستورَدة على مستوى وحدة ``main`` وتُستخدَم حصريّاً من هذه
الـendpoints؛ نُقل استيرادها هنا (من المصدر مباشرةً) لتفادي استيراد يتيم في
``main`` بعد النقل — لا تغيير سلوكيّ.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    ShareKeyRequest,
    SharingKeyCreateRequest,
    UserSchema,
    get_current_user,
    get_pool,
    require_permission,
    tenant_connection,
)
from api.sharing import (
    SharingKeyService,
    SharingScope,
    ThirdPartyType,
    generate_key_plaintext,
    hash_key,
)
from api.sharing import SharingScope as _SScope
from api.sharing import ThirdPartyType as _TPType

router = APIRouter()


@router.post("/api/v1/sharing/generate-key")
def generate_share_key(
    req: ShareKeyRequest,
    user: UserSchema = Depends(require_permission(Permission.USER_INVITE)),
):
    """يولّد مفتاح مشاركة (يُعرَض الـplaintext مرّة واحدة فقط).

    ملاحظة: الحفظ في DB يحتاج PostgreSQL (غير موصَّل). هذا يولّد المفتاح
    والـhash والبيانات الوصفيّة — جاهزة للحفظ لاحقاً.
    """
    try:
        scope = SharingScope(req.scope)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"نطاق غير صالح: {req.scope}") from None
    tp_type = None
    if req.third_party_type:
        try:
            tp_type = ThirdPartyType(req.third_party_type)
        except ValueError:
            raise HTTPException(
                status_code=422, detail=f"نوع طرف غير صالح: {req.third_party_type}"
            ) from None

    plaintext = generate_key_plaintext()
    now = datetime.now(UTC)
    return {
        "key_id": str(_uuid.uuid4()),
        "key_plaintext": plaintext,  # يُعرَض مرّة واحدة
        "key_hash": hash_key(plaintext),  # للحفظ في DB
        "key_prefix": plaintext[:12],
        "scope": scope.value,
        "third_party_name": req.third_party_name,
        "third_party_type": tp_type.value if tp_type else None,
        "allowed_field_ids": req.allowed_field_ids,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=req.expires_in_days)).isoformat(),
        "note_ar": "احفظ هذا المفتاح الآن — لن يُعرَض مرّة أخرى. الحفظ في قاعدة البيانات يحتاج تفعيل الخادم.",
    }


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
            "expires_at": key.expires_at,
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
