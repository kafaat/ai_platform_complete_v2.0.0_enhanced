"""api/routers/auth.py — المصادقة والجلسات (Authentication & Sessions)
======================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الأربع حرفيّاً مع تغيير ``@app`` إلى ``@router``.
منطق المصادقة/التوكن لم يُمسّ (نقطة dev معطّلة افتراضيّاً، إبطال jti عبر denylist).

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات/الأسرار) تبقى مُعرَّفة في
``api.main`` وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات
الاختبارات. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته
فقط (بعد تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

import time

import jwt  # PyJWT
from fastapi import APIRouter, Depends, Header, HTTPException
from jwt.exceptions import InvalidTokenError

import api.main as _main
from api.main import (
    _ALLOWED_ISS,
    _DEV_AUTH_ENABLED,
    JWT_ALGORITHM,
    JWT_EXPIRY_HOURS,
    JWT_SECRET,
    LoginRequest,
    TokenResponse,
    UserRole,
    UserSchema,
    create_token,
    get_current_user,
    logger,
)

# ملاحظة: ``_DENYLIST`` يُقرأ عبر ``_main._DENYLIST`` عند الاستدعاء (لا يُربَط وقت
# الاستيراد) كي يبقى السلوك مطابقاً لما كان في main: مرجع وحدة قابل لإعادة الربط
# (get_current_user يقرؤه كذلك، والاختبارات تُرقّع api.main._DENYLIST).

router = APIRouter()


@router.post("/api/v1/auth/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """تسجيل دخول dev-mode (بلا كلمة مرور). مُعطَّل افتراضيّاً في كلّ البيئات؛
    لا يُفعَّل إلّا بـSAHOOL_DEV_AUTH=1 وفي غير الإنتاج. غير ذلك ⇒ 403.
    المصادقة الحقيقيّة عبر خدمة sahool-auth (/auth/login بـbcrypt)."""
    # C1 FIX: هذه نقطة تطوير تُصدر JWT بلا كلمة مرور. مُعطَّلة افتراضيّاً (وفي
    # الإنتاج دائماً) — لا تُفعَّل إلّا بإقرار صريح SAHOOL_DEV_AUTH=1 في غير الإنتاج.
    # يمنع تجاوز المصادقة وانهيار عزل المستأجرين لو أصابت الطلبات هذه النقطة.
    if not _DEV_AUTH_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="نقطة dev معطّلة — استخدم خدمة المصادقة (/auth/login).",
        )
    # هنا: dev-mode فقط، نقبل أيّ user_id صالح
    try:
        role = UserRole(req.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}") from None

    user = UserSchema(
        user_id=req.user_id,
        tenant_id=req.tenant_id,
        role=role,
        name_ar=req.name_ar,
    )
    token = create_token(user)

    return TokenResponse(
        access_token=token,
        expires_in=JWT_EXPIRY_HOURS * 3600,
        user={
            "user_id": user.user_id,
            "tenant_id": user.tenant_id,
            "role": user.role.value,
            "name_ar": user.name_ar,
        },
    )


# ─── auth endpoints التي يطلبها التطبيق (مطابقة contract) ─────────
# جلسة المطابقة: الموبايل (authService.ts) يستدعي /api/v1/auth/{me,logout,signup}
# لكنّها لم تكن موجودة → تسجيل الدخول/الخروج كان يفشل بـ404.


@router.get("/api/v1/auth/me")
def auth_me(user: UserSchema = Depends(get_current_user)):
    """alias لـ/api/v1/me — التطبيق يستدعي هذا المسار."""
    return {
        "user": {
            "user_id": user.user_id,
            "tenant_id": user.tenant_id,
            "role": user.role.value,
            "name_ar": user.name_ar,
        }
    }


@router.post("/api/v1/auth/logout")
def auth_logout(
    authorization: str = Header(None),
    user: UserSchema = Depends(get_current_user),
):
    """تسجيل خروج — يُبطِل التوكن فعليّاً عبر denylist (jti) لا على الجهاز فقط.

    يُضيف jti التوكن للقائمة بمهلة = ما تبقّى حتى انتهائه، فيُرفَض في الطلبات اللاحقة
    (get_current_user يستشير القائمة). fail-safe: فشل الإبطال لا يكسر الخروج.
    """
    token = (authorization or "").replace("Bearer ", "", 1)
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], audience="sahool")
        # تدقيق B: افرض المُصدِر — توكن من مُصدِر مجهول يُعامَل كغير صالح (لا إبطال له).
        if payload.get("iss") not in _ALLOWED_ISS:
            raise InvalidTokenError("Invalid token issuer")
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            ttl = max(1, int(exp) - int(time.time()))
            _main._DENYLIST.revoke(jti, ttl)
    except Exception as e:  # noqa: BLE001 — فشل الإبطال لا يكسر الخروج (العميل يحذف التوكن)
        logger.warning("logout: تعذّر إبطال التوكن: %s", e)
    return {"status": "logged_out", "message_ar": "تمّ تسجيل الخروج"}


@router.post("/api/v1/auth/signup", response_model=TokenResponse)
def auth_signup(req: LoginRequest):
    """تسجيل مستخدم جديد (dev-mode — نفس منطق login بلا كلمة مرور).

    مُعطَّل افتراضيّاً في كلّ البيئات؛ لا يُفعَّل إلّا بـSAHOOL_DEV_AUTH=1 وفي غير
    الإنتاج. غير ذلك ⇒ 403. التسجيل الحقيقيّ عبر خدمة auth (DB + bcrypt).
    """
    # C1 FIX: نفس منطق login بلا كلمة مرور → مُعطَّل افتراضيّاً وفي الإنتاج دائماً.
    if not _DEV_AUTH_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="نقطة dev معطّلة — استخدم خدمة المصادقة.",
        )
    try:
        role = UserRole(req.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}") from None
    user = UserSchema(
        user_id=req.user_id,
        tenant_id=req.tenant_id,
        role=role,
        name_ar=req.name_ar,
    )
    token = create_token(user)
    return TokenResponse(
        access_token=token,
        expires_in=JWT_EXPIRY_HOURS * 3600,
        user={
            "user_id": user.user_id,
            "tenant_id": user.tenant_id,
            "role": user.role.value,
            "name_ar": user.name_ar,
        },
    )
