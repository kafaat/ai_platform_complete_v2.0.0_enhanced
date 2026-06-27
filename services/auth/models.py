"""نماذج الطلب/الاستجابة (Pydantic) لخدمة المصادقة — معزولة عن FastAPI/Redis/DB.

استُخرِجت حرفيّاً من main.py لتقليص حجمه وفصل عقود البيانات (schemas) عن المنطق.
main.py يعيد استيرادها وتصديرها كما هي (سلوك محفوظ، لا تغيير في الحقول/التحقّق).
لا تستورد هذه الوحدة من main.py (تفادي الاستيراد الدائريّ) — تعتمد فقط على otp
(ثوابت OTP النقيّة) وpydantic.
"""

from __future__ import annotations

from typing import Literal

from otp import OTP_LENGTH
from pydantic import BaseModel, EmailStr, Field, field_validator

# الدور المدعوّ إليه — Literal يرفض owner/admin عند التحقّق (422) قبل أيّ منطق.
InviteableRole = Literal["expert", "farmer", "viewer"]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=100)
    # ملاحظة أمنيّة: لا حقل role هنا عمداً — العميل لا يختار دوره. التسجيل الذاتيّ
    # يُنشئ مستأجِراً معزولاً جديداً ويُسنِد 'owner' (مؤسِّس مستأجِره؛ انظر register).
    # تغيير الأدوار عبر /auth/users/{id}/role المحمي بـadmin فقط (منع تصعيد الصلاحيات).

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على حرف كبير")
        if not any(c.isdigit() for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رقم")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رمز خاص")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = None  # رمز TOTP المؤقّت — مطلوب إن كان MFA مفعّلاً للحساب


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=10)  # رمز TOTP (٦ أرقام عادةً)


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على حرف كبير")
        if not any(c.isdigit() for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رقم")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ── Invitation models ──────────────────────────────────────────
class InvitationCreateRequest(BaseModel):
    email: EmailStr
    # InviteableRole (Literal) يرفض owner/admin بـ422 قبل المنطق — حزام أوّل ضدّ
    # تصعيد الصلاحيّات؛ يليه فحص is_inviteable_role صريح في المعالِج (دفاع عمق).
    role: InviteableRole


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=100)

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على حرف كبير")
        if not any(c.isdigit() for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رقم")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رمز خاص")
        return v


# ── Tenant provisioning model (تهيئة مستأجِر B2B بيد مدير المنصّة) ────
class TenantProvisionRequest(BaseModel):
    """طلب تهيئة مستأجِر جديد + أوّل مالك له (إعداد B2B، لا تسجيل ذاتيّ).

    لا حقل role/password/tenant_id هنا عمداً: الدور دائماً 'owner' (يُفرَض في
    المعالِج)، والمالك يضبط كلمة مروره لاحقاً عبر رمز إعادة تعيين (لا كلمة مرور
    من المُهيِّئ)، والمستأجِر جديد معزول (gen_random_uuid) لا يختاره المُهيِّئ
    (منع تصادم/تصعيد). tenant_name اختياريّ ويُسجَّل في التدقيق فقط — لا يوجد
    جدول tenants؛ المستأجرون ضمنيّون عبر users.tenant_id (اتّساقاً مع التسجيل الذاتيّ).
    """

    owner_email: EmailStr
    owner_full_name: str = Field(min_length=2, max_length=100)
    tenant_name: str | None = Field(default=None, max_length=200)


# قناة التحقّق: بريد أو هاتف. Literal يرفض أيّ قيمة أخرى عند التحقّق (422).
VerifyChannel = Literal["email", "phone"]


class VerificationRequest(BaseModel):
    channel: VerifyChannel


class VerificationConfirm(BaseModel):
    channel: VerifyChannel
    # رمز رقميّ ٦ خانات. نسمح بحدود واسعة قليلاً للتشذيب ثمّ نتحقّق نقيّاً.
    code: str = Field(min_length=OTP_LENGTH, max_length=OTP_LENGTH)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int  # seconds
    user_id: int
    role: str
    full_name: str
    tenant_id: str
