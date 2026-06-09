"""
sahool_core.schema_factory
============================
Factory functions لـcanonical_schemas — يربط canonical_schemas مع identity.

الفجوة المُسدّاة من المراجعة الشاملة (ت٢):
  "Canonical Schemas + Identity — تكامل ضعيف. لا 'مُولَّد افتراضي'.
   لو أنشأ المطوّر FieldSchema(...) بدون id_uuid، تبقى None للأبد.
   Dual-ID يحضر في النواة لكن لا أحد يستخدمه فعلاً."

الحلّ: factories تستدعي identity.new_identity() تلقائياً.

النمط:
  • canonical_schemas تحتفظ بالتوافق الخلفي (id_uuid اختياري)
  • schema_factory هي الطريق الموصى به الجديد
  • generate_uuid يحدث افتراضياً، readable_id يُولَّد من السياق

التمييز عن canonical_schemas المباشر:
  ✓ FieldSchema(field_id="x", ...)         → id_uuid=None (legacy support)
  ✓ make_field(name="x", farm="y", ...)    → id_uuid يُولَّد تلقائياً

المبادئ المحفوظة:
  • التوافق الخلفي: canonical_schemas المباشر لم يتغيّر
  • صفر اختراع: factory يفشل صراحةً إن نقصت بيانات إلزامية
  • صراحة العقد: كل factory يُعلِم بـtenant + entity kind
"""
from __future__ import annotations

from datetime import datetime

from core.canonical_schemas import (
    TenantSchema, UserSchema, FarmSchema, FieldSchema, CropSeasonSchema,
    ObservationSchema, RecommendationSchema,
    UserRole, FieldQuality, IrrigationMethod, SeasonStatus,
    ObservationSource, TenantStatus)
from core.identity import EntityKind, new_identity


def make_tenant(*, name_ar: str,
                tenant_id_readable: str | None = None,
                **kwargs) -> TenantSchema:
    """ينشئ TenantSchema مع UUID + readable id تلقائياً.

    tenant_id_readable: لو حُدّد، يُستخدم كما هو (للترقية).
                       إن لم يُحدّد، يُولَّد من name_ar."""
    if tenant_id_readable:
        readable = tenant_id_readable
        # توليد UUID فقط
        from core.identity import generate_uuid
        uuid_str = generate_uuid()
    else:
        # توليد كلاهما من السياق
        context = name_ar[:20] if name_ar else None
        pair = new_identity(EntityKind.TENANT, context=context)
        readable = pair.readable
        uuid_str = pair.uuid

    return TenantSchema(
        tenant_id=readable,
        name_ar=name_ar,
        id_uuid=uuid_str,
        created_at=datetime.now().isoformat(),
        **kwargs,
    )


def make_user(*, tenant_id: str, role: UserRole, name_ar: str,
              user_id_readable: str | None = None,
              **kwargs) -> UserSchema:
    """ينشئ UserSchema مع Dual-ID."""
    if user_id_readable:
        readable = user_id_readable
        from core.identity import generate_uuid
        uuid_str = generate_uuid()
    else:
        # tenant_id_short للسياق
        context = f"{tenant_id[:8]}_{role.value}"
        pair = new_identity(EntityKind.USER, context=context)
        readable = pair.readable
        uuid_str = pair.uuid

    return UserSchema(
        user_id=readable,
        tenant_id=tenant_id,
        role=role,
        name_ar=name_ar,
        id_uuid=uuid_str,
        created_at=datetime.now().isoformat(),
        **kwargs,
    )


def make_farm(*, tenant_id: str, name_ar: str,
              farm_id_readable: str | None = None,
              **kwargs) -> FarmSchema:
    """ينشئ FarmSchema مع Dual-ID."""
    if farm_id_readable:
        readable = farm_id_readable
        from core.identity import generate_uuid
        uuid_str = generate_uuid()
    else:
        context = f"{tenant_id[:8]}"
        pair = new_identity(EntityKind.FARM, context=context)
        readable = pair.readable
        uuid_str = pair.uuid

    return FarmSchema(
        farm_id=readable,
        tenant_id=tenant_id,
        name_ar=name_ar,
        id_uuid=uuid_str,
        created_at=datetime.now().isoformat(),
        **kwargs,
    )


def make_field(*, tenant_id: str, farm_id: str, name_ar: str,
               field_id_readable: str | None = None,
               **kwargs) -> FieldSchema:
    """ينشئ FieldSchema مع Dual-ID. الحقل الأساسي للمنصّة."""
    if field_id_readable:
        readable = field_id_readable
        from core.identity import generate_uuid
        uuid_str = generate_uuid()
    else:
        context = f"{farm_id[:12]}"
        pair = new_identity(EntityKind.FIELD, context=context)
        readable = pair.readable
        uuid_str = pair.uuid

    return FieldSchema(
        field_id=readable,
        tenant_id=tenant_id,
        farm_id=farm_id,
        name_ar=name_ar,
        id_uuid=uuid_str,
        created_at=datetime.now().isoformat(),
        **kwargs,
    )


def make_crop_season(*, tenant_id: str, field_id: str, crop_id: str,
                     season_name_ar: str, season_year: int,
                     season_id_readable: str | None = None,
                     **kwargs) -> CropSeasonSchema:
    """ينشئ CropSeasonSchema مع Dual-ID."""
    if season_id_readable:
        readable = season_id_readable
        from core.identity import generate_uuid
        uuid_str = generate_uuid()
    else:
        context = f"{crop_id}_{season_year}"
        pair = new_identity(EntityKind.SEASON, context=context)
        readable = pair.readable
        uuid_str = pair.uuid

    return CropSeasonSchema(
        season_id=readable,
        tenant_id=tenant_id,
        field_id=field_id,
        crop_id=crop_id,
        season_name_ar=season_name_ar,
        season_year=season_year,
        id_uuid=uuid_str,
        **kwargs,
    )


def make_observation(*, tenant_id: str, field_id: str,
                     observable_id: str, value: float, unit: str,
                     source: ObservationSource, confidence: str,
                     measured_at: str,
                     observation_id_readable: str | None = None,
                     **kwargs) -> ObservationSchema:
    """ينشئ ObservationSchema مع Dual-ID. وحدة EAV الأساسية."""
    if observation_id_readable:
        readable = observation_id_readable
        from core.identity import generate_uuid
        uuid_str = generate_uuid()
    else:
        context = f"{observable_id}_{source.value}"
        pair = new_identity(EntityKind.OBSERVATION, context=context)
        readable = pair.readable
        uuid_str = pair.uuid

    return ObservationSchema(
        observation_id=readable,
        tenant_id=tenant_id,
        field_id=field_id,
        observable_id=observable_id,
        value=value,
        unit=unit,
        source=source,
        confidence=confidence,
        measured_at=measured_at,
        id_uuid=uuid_str,
        created_at=datetime.now().isoformat(),
        **kwargs,
    )


def make_recommendation(*, tenant_id: str,
                        recommendation_ar: str,
                        rec_id_readable: str | None = None,
                        **kwargs) -> RecommendationSchema:
    """ينشئ RecommendationSchema مع Dual-ID."""
    if rec_id_readable:
        readable = rec_id_readable
        from core.identity import generate_uuid
        uuid_str = generate_uuid()
    else:
        context = datetime.now().strftime("%Y%m%d_%H%M%S")
        pair = new_identity(EntityKind.RECOMMENDATION, context=context)
        readable = pair.readable
        uuid_str = pair.uuid

    return RecommendationSchema(
        rec_id=readable,
        tenant_id=tenant_id,
        recommendation_ar=recommendation_ar,
        issued_date=kwargs.pop("issued_date",
                              datetime.now().date().isoformat()),
        id_uuid=uuid_str,
        **kwargs,
    )


def make_default_pair_for_entity(kind: EntityKind,
                                  context: str | None = None) -> tuple:
    """يُرجع (uuid, readable) لأيّ نوع — useful للهجرة من schemas قديمة."""
    pair = new_identity(kind, context=context)
    return pair.uuid, pair.readable
