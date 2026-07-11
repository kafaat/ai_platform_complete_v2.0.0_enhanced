"""
sahool_core.authorization
==========================
RBAC + Farm Hierarchy — الحراسة المتعدّدة المستأجرين.

الفجوة المسدودة: tenant_id موجود في كل الجداول، لكن لا roles ولا
Farm hierarchy حقيقية. مع مئات المستخدمين، هذا فجوة أمنية حرجة:
كيف نضمن أن مهندس زراعي يرى توصيات حقوله فقط، لا حقول مزارع أخرى؟

الطبقات الثلاث للحراسة:
  ١. tenant_id              ← الخطّ الأحمر المطلق
                              لا cross-tenant queries أبداً
  ٢. user.role              ← ماذا يستطيع المستخدم فعله؟
  ٣. user.farm_ids_access   ← أيّ مزارع داخل tenant يصل لها؟

التمييز عن أنظمة كبيرة (Cropwise/Salesforce):
  • لا schema-per-tenant (tenant_id كافٍ < 200 مستأجر)
  • لا OAuth2/SSO/MFA في النواة (طبقة API لاحقاً)
  • لا UUID مفروض (TEXT id يكفي، Dual-ID لاحقاً)

المبادئ:
  • Fail closed: شكّ = منع. السماح صريح.
  • Defense in depth: tenant ثم role ثم farm — كلها يجب أن تنجح
  • Audit-ready: كل قرار صلاحية يحمل سبباً
  • محايد عن مصدر الـuser (DB/JWT/header) — يأخذ UserSchema جاهزة

التكامل:
  ← يأخذ UserSchema من canonical_schemas
  ← يحرس استدعاءات skills_registry (لاحقاً)
  ← يحرس cross_reference_finder (تفعيل عزل tenant آلياً)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.canonical_schemas import UserRole, UserSchema


class Permission(str, Enum):
    """العمليات الجوهرية في النواة. مفصّلة عمداً لتجنّب 'صلاحية شاملة'."""

    # المزارع والحقول
    FARM_CREATE = "farm:create"
    FARM_EDIT = "farm:edit"
    FARM_DELETE = "farm:delete"
    FARM_VIEW = "farm:view"
    FIELD_CREATE = "field:create"
    FIELD_EDIT = "field:edit"
    FIELD_DELETE = "field:delete"
    FIELD_VIEW = "field:view"
    # التوصيات
    RECOMMENDATION_REQUEST = "recommendation:request"
    RECOMMENDATION_VIEW = "recommendation:view"
    RECOMMENDATION_OVERRIDE = "recommendation:override"  # حرج
    DECISION_APPROVE = "decision:approve"  # WX-10.7: مراجعة/موافقة مرشّح القرار (حرج)
    DECISION_DISPATCH_AUTHORIZE = "decision:dispatch-authorize"  # WX-10.10: تفويض الإرسال فقط
    DECISION_EXECUTE = "decision:execute"  # WX-10.11a: إنشاء طلب تنفيذ authoritative
    # الأنشطة
    ACTIVITY_PLAN = "activity:plan"
    ACTIVITY_EXECUTE = "activity:execute"  # mark_completed
    ACTIVITY_SKIP = "activity:skip"  # mark_skipped
    ACTIVITY_VIEW = "activity:view"
    # البيانات
    OBSERVATION_RECORD = "observation:record"
    OBSERVATION_VIEW = "observation:view"
    HISTORICAL_IMPORT = "historical:import"  # historical_loader
    # السلامة (حرجة)
    PESTICIDE_APPROVE = "pesticide:approve"  # safety_critical
    HARVEST_AUTHORIZE = "harvest:authorize"  # PHI gate override
    # الإدارة
    USER_INVITE = "user:invite"
    USER_REMOVE = "user:remove"
    USER_CHANGE_ROLE = "user:change_role"
    CALIBRATION_RUN = "calibration:run"
    # المخزون والمعدّات (إدارة الموارد — الطبقتان ١٠/١١ من تدقيق التغطية)
    INVENTORY_VIEW = "inventory:view"
    INVENTORY_MANAGE = "inventory:manage"  # إضافة/تعديل دفعات، خصم كمّيّات
    EQUIPMENT_VIEW = "equipment:view"
    EQUIPMENT_MANAGE = "equipment:manage"  # تسجيل معدّة/صيانة/عطل
    # أجهزة IoT (سجلّ + صحّة + telemetry — الطبقة ٤ من تدقيق التغطية)
    DEVICE_VIEW = "device:view"
    DEVICE_MANAGE = "device:manage"  # تسجيل/تعطيل جهاز، إدارة السجلّ
    # الري التشغيلي (جدولة + صمامات — الطبقة ٣ من تدقيق التغطية)
    IRRIGATION_VIEW = "irrigation:view"
    IRRIGATION_MANAGE = "irrigation:manage"  # جدولة، تسجيل صمّام، أمر فتح/إغلاق
    # البيانات المرجعيّة (Master Data: محاصيل/تربة/أسمدة/مبيدات/بذور — الطبقة المركزيّة)
    MASTER_DATA_VIEW = "master_data:view"
    MASTER_DATA_MANAGE = "master_data:manage"
    # الإعدادات (Settings: منصّة/مزرعة/ريّ/إشعارات — مخزن مفتاح/قيمة لكلّ مستأجر)
    SETTINGS_VIEW = "settings:view"
    SETTINGS_MANAGE = "settings:manage"
    # إدارة المستندات (Document Management: عقود/تقارير/صور/خرائط/نتائج مختبر)
    DOCUMENT_VIEW = "document:view"
    DOCUMENT_MANAGE = "document:manage"
    # التحليلات (تكاليف فعليّة مُجمَّعة — استبدال ملخّص ReportsPage الثابت)
    ANALYTICS_VIEW = "analytics:view"
    # التقارير والمراجعة
    AUDIT_VIEW = "audit:view"
    REPLAY_RECOMMENDATION = "replay:recommendation"  # recommendation_replay
    # ── إدارة المنصّة (نطاق platform_admin — منفصل عن بيانات المستأجِر) ──
    PLATFORM_MANAGE = "platform:manage"  # إدارة بنية/خدمات/مستأجِرين على مستوى المنصّة


# ─── مصفوفة الصلاحيات الافتراضية ──────────────────────────────────
# جدول صريح بدلاً من inheritance المُربك. كل دور يُعلن صلاحياته.
_ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.OWNER: {
        # كل شيء — لكن صريحاً (لا magic admin)
        Permission.FARM_CREATE,
        Permission.FARM_EDIT,
        Permission.FARM_DELETE,
        Permission.FARM_VIEW,
        Permission.FIELD_CREATE,
        Permission.FIELD_EDIT,
        Permission.FIELD_DELETE,
        Permission.FIELD_VIEW,
        Permission.RECOMMENDATION_REQUEST,
        Permission.RECOMMENDATION_VIEW,
        Permission.RECOMMENDATION_OVERRIDE,
        Permission.DECISION_APPROVE,
        Permission.DECISION_DISPATCH_AUTHORIZE,
        Permission.DECISION_EXECUTE,
        Permission.ACTIVITY_PLAN,
        Permission.ACTIVITY_EXECUTE,
        Permission.ACTIVITY_SKIP,
        Permission.ACTIVITY_VIEW,
        Permission.OBSERVATION_RECORD,
        Permission.OBSERVATION_VIEW,
        Permission.HISTORICAL_IMPORT,
        Permission.PESTICIDE_APPROVE,
        Permission.HARVEST_AUTHORIZE,
        Permission.USER_INVITE,
        Permission.USER_REMOVE,
        Permission.USER_CHANGE_ROLE,
        Permission.CALIBRATION_RUN,
        Permission.AUDIT_VIEW,
        Permission.REPLAY_RECOMMENDATION,
        Permission.INVENTORY_VIEW,
        Permission.INVENTORY_MANAGE,
        Permission.EQUIPMENT_VIEW,
        Permission.EQUIPMENT_MANAGE,
        Permission.DEVICE_VIEW,
        Permission.DEVICE_MANAGE,
        Permission.IRRIGATION_VIEW,
        Permission.IRRIGATION_MANAGE,
        Permission.MASTER_DATA_VIEW,
        Permission.MASTER_DATA_MANAGE,
        Permission.SETTINGS_VIEW,
        Permission.SETTINGS_MANAGE,
        Permission.DOCUMENT_VIEW,
        Permission.DOCUMENT_MANAGE,
        Permission.ANALYTICS_VIEW,
    },
    UserRole.MANAGER: {
        # إدارة كاملة، لا حذف ملكية ولا تغيير أدوار
        Permission.FARM_VIEW,
        Permission.FARM_EDIT,
        Permission.FIELD_CREATE,
        Permission.FIELD_EDIT,
        Permission.FIELD_VIEW,
        Permission.RECOMMENDATION_REQUEST,
        Permission.RECOMMENDATION_VIEW,
        Permission.DECISION_APPROVE,
        Permission.DECISION_DISPATCH_AUTHORIZE,
        Permission.DECISION_EXECUTE,
        Permission.ACTIVITY_PLAN,
        Permission.ACTIVITY_EXECUTE,
        Permission.ACTIVITY_SKIP,
        Permission.ACTIVITY_VIEW,
        Permission.OBSERVATION_RECORD,
        Permission.OBSERVATION_VIEW,
        Permission.HISTORICAL_IMPORT,
        Permission.CALIBRATION_RUN,
        Permission.AUDIT_VIEW,
        Permission.REPLAY_RECOMMENDATION,
        Permission.USER_INVITE,  # دعوة، لا تغيير أدوار
        Permission.INVENTORY_VIEW,
        Permission.INVENTORY_MANAGE,
        Permission.EQUIPMENT_VIEW,
        Permission.EQUIPMENT_MANAGE,
        Permission.DEVICE_VIEW,
        Permission.DEVICE_MANAGE,
        Permission.IRRIGATION_VIEW,
        Permission.IRRIGATION_MANAGE,
        Permission.MASTER_DATA_VIEW,
        Permission.MASTER_DATA_MANAGE,
        Permission.SETTINGS_VIEW,
        Permission.SETTINGS_MANAGE,
        Permission.DOCUMENT_VIEW,
        Permission.DOCUMENT_MANAGE,
        Permission.ANALYTICS_VIEW,
    },
    UserRole.AGRONOMIST: {
        # توصيات + معايرة + بحث، لا إدارة بنيوية
        Permission.FARM_VIEW,
        Permission.FIELD_VIEW,
        Permission.RECOMMENDATION_REQUEST,
        Permission.RECOMMENDATION_VIEW,
        Permission.DECISION_APPROVE,
        Permission.ACTIVITY_PLAN,
        Permission.ACTIVITY_VIEW,
        Permission.OBSERVATION_RECORD,
        Permission.OBSERVATION_VIEW,
        Permission.HISTORICAL_IMPORT,
        Permission.CALIBRATION_RUN,
        Permission.REPLAY_RECOMMENDATION,
        Permission.PESTICIDE_APPROVE,  # المهندس يوافق على المبيدات
        # لا HARVEST_AUTHORIZE (تخطّي PHI يحتاج OWNER)
        Permission.INVENTORY_VIEW,  # يرى المخزون (أيّ مبيدات/أسمدة متوفّرة)
        Permission.EQUIPMENT_VIEW,
        Permission.DEVICE_VIEW,
        Permission.IRRIGATION_VIEW,
        Permission.IRRIGATION_MANAGE,
        Permission.MASTER_DATA_VIEW,
        Permission.MASTER_DATA_MANAGE,
        Permission.SETTINGS_VIEW,
        Permission.DOCUMENT_VIEW,
        Permission.DOCUMENT_MANAGE,
        Permission.ANALYTICS_VIEW,
    },
    UserRole.WORKER: {
        # تنفيذ ميداني فقط
        Permission.FARM_VIEW,
        Permission.FIELD_VIEW,
        Permission.RECOMMENDATION_VIEW,
        Permission.ACTIVITY_EXECUTE,
        Permission.ACTIVITY_SKIP,
        Permission.ACTIVITY_VIEW,
        Permission.OBSERVATION_RECORD,
        Permission.OBSERVATION_VIEW,
        Permission.INVENTORY_VIEW,  # يرى المخزون والمعدّات المتاحة للتنفيذ
        Permission.EQUIPMENT_VIEW,
        Permission.DEVICE_VIEW,
        Permission.IRRIGATION_VIEW,
        Permission.MASTER_DATA_VIEW,
        Permission.SETTINGS_VIEW,
        Permission.DOCUMENT_VIEW,
    },
    UserRole.VIEWER: {
        # قراءة فقط
        Permission.FARM_VIEW,
        Permission.FIELD_VIEW,
        Permission.RECOMMENDATION_VIEW,
        Permission.ACTIVITY_VIEW,
        Permission.OBSERVATION_VIEW,
        Permission.INVENTORY_VIEW,
        Permission.EQUIPMENT_VIEW,
        Permission.DEVICE_VIEW,
        Permission.IRRIGATION_VIEW,
        Permission.MASTER_DATA_VIEW,
        Permission.SETTINGS_VIEW,
        Permission.DOCUMENT_VIEW,
    },
    # مدير المنصّة: نطاق إداريّ منفصل عن بيانات المستأجِر. يدير المستخدمين والتدقيق
    # وحوكمة الأحداث الفاشلة (DLQ) وإعدادات المنصّة — لكنّه **لا يملك** أيّ صلاحية على
    # بيانات المستأجِر (حقول/توصيات/أنشطة/ري/مخزون…). هذا يُجسّد `platform_admin ≠
    # tenant_owner`: الوصول لبيانات مستأجِر يكون عبر break-glass صريح (دور مؤقّت
    # tenant-scoped بسبب+مدّة+MFA+تدقيق) لا تلقائيّاً عبر هذا الدور.
    UserRole.PLATFORM_ADMIN: {
        Permission.PLATFORM_MANAGE,  # إدارة المنصّة/تهيئة المستأجرين (نطاق منصّة لا tenant)
        Permission.AUDIT_VIEW,  # حوكمة DLQ + سجلّ الأمان (admin_router)
        Permission.ANALYTICS_VIEW,
        Permission.SETTINGS_VIEW,
        # ملاحظة: عمداً **بلا** USER_INVITE/USER_REMOVE/USER_CHANGE_ROLE — تلك إدارة
        # مستخدمي **المستأجِر** (مهمّة tenant_owner؛ تحفظها لامركزيّةُ منع تصعيد
        # الصلاحيات). تهيئة مستأجِر جديد + أوّل مالك تكون عبر نقطة منصّة مُبوّبة
        # بـPLATFORM_MANAGE (بند لاحق)، لا عبر صلاحيات مستخدمي المستأجِر.
    },
}


@dataclass
class AuthDecision:
    """قرار صلاحية بسبب صريح — قابل للمراجعة."""

    allowed: bool
    reason_ar: str
    user_id: str | None = None
    role: str | None = None
    permission: str | None = None
    tenant_id: str | None = None
    resource_tenant_id: str | None = None
    farm_id: str | None = None


def has_permission(user: UserSchema, permission: Permission) -> bool:
    """فحص أساسي: هل دور المستخدم يملك الصلاحية؟"""
    if not user.is_active:
        return False
    return permission in _ROLE_PERMISSIONS.get(user.role, set())


def authorize(
    user: UserSchema,
    permission: Permission,
    *,
    resource_tenant_id: str | None = None,
    farm_id: str | None = None,
) -> AuthDecision:
    """قرار صلاحية كامل — الثلاث طبقات معاً.

    الفحوصات بالترتيب (Fail closed):
      1. المستخدم نشط؟
      2. الدور يملك الصلاحية؟
      3. tenant يطابق resource؟  ← الخطّ الأحمر
      4. الحقل (إن وُجد) ضمن farm_ids_access؟"""

    base = AuthDecision(
        allowed=False,
        reason_ar="",
        user_id=user.user_id,
        role=user.role.value,
        permission=permission.value,
        tenant_id=user.tenant_id,
        resource_tenant_id=resource_tenant_id,
        farm_id=farm_id,
    )

    # 1. نشاط المستخدم
    if not user.is_active:
        base.reason_ar = f"المستخدم {user.user_id} غير نشط"
        return base

    # 2. صلاحية الدور
    role_perms = _ROLE_PERMISSIONS.get(user.role, set())
    if permission not in role_perms:
        base.reason_ar = f"الدور '{user.role.value}' لا يملك صلاحية '{permission.value}'"
        return base

    # 3. عزل tenant — الخطّ الأحمر المطلق
    if resource_tenant_id is not None and resource_tenant_id != user.tenant_id:
        base.reason_ar = (
            f"عزل tenant: المستخدم في '{user.tenant_id}'، المورد في '{resource_tenant_id}'"
        )
        return base

    # 4. صلاحية الوصول للمزرعة (إن طُلب)
    # farm_ids_access فارغة = كل المزارع في tenant
    if farm_id is not None:
        if user.farm_ids_access and farm_id not in user.farm_ids_access:
            base.reason_ar = (
                f"المستخدم ليس له صلاحية على المزرعة '{farm_id}' (الوصول: {user.farm_ids_access})"
            )
            return base

    base.allowed = True
    base.reason_ar = f"مسموح: {user.role.value} لـ{permission.value}" + (
        f" في {farm_id}" if farm_id else ""
    )
    return base


# ─── Farm Hierarchy Helpers ──────────────────────────────────────


def farms_accessible_to_user(user: UserSchema, all_farms_in_tenant: list) -> list:
    """المزارع التي يستطيع المستخدم رؤيتها.

    قاعدة: farm_ids_access فارغة = كل المزارع في tenant.
    غير فارغة = حصراً ما فيها."""
    if not user.is_active:
        return []
    if not user.farm_ids_access:  # empty = all
        return [f for f in all_farms_in_tenant if f.tenant_id == user.tenant_id]
    return [
        f
        for f in all_farms_in_tenant
        if f.tenant_id == user.tenant_id and f.farm_id in user.farm_ids_access
    ]


def fields_in_farm_for_user(user: UserSchema, farm_id: str, all_fields: list) -> list:
    """الحقول داخل مزرعة، مع تطبيق الصلاحيات.

    شرط مزدوج: tenant_id يطابق + الحقل في المزرعة + المستخدم يصل للمزرعة."""
    # تحقّق صلاحية المزرعة أولاً
    decision = authorize(
        user, Permission.FIELD_VIEW, resource_tenant_id=user.tenant_id, farm_id=farm_id
    )
    if not decision.allowed:
        return []
    return [f for f in all_fields if f.tenant_id == user.tenant_id and f.farm_id == farm_id]


# ─── Audit Helpers ───────────────────────────────────────────────


def audit_user_permissions(user: UserSchema) -> dict:
    """تقرير: ما يستطيع هذا المستخدم فعله؟ مفيد للواجهة وللمراجعة."""
    perms = _ROLE_PERMISSIONS.get(user.role, set())
    return {
        "user_id": user.user_id,
        "tenant_id": user.tenant_id,
        "role": user.role.value,
        "is_active": user.is_active,
        "permissions_count": len(perms),
        "permissions": sorted(p.value for p in perms),
        "farm_access": ("all_in_tenant" if not user.farm_ids_access else user.farm_ids_access),
        "summary_ar": (
            f"المستخدم {user.user_id} ({user.role.value}) "
            f"لديه {len(perms)} صلاحية في tenant {user.tenant_id}"
        ),
    }


def is_safety_critical_permission(permission: Permission) -> bool:
    """صلاحيات حرجة تحتاج double-check (تطابق مع skills_registry)."""
    critical = {
        Permission.PESTICIDE_APPROVE,
        Permission.HARVEST_AUTHORIZE,
        Permission.RECOMMENDATION_OVERRIDE,
        Permission.USER_CHANGE_ROLE,
        Permission.FARM_DELETE,
        Permission.FIELD_DELETE,
    }
    return permission in critical
