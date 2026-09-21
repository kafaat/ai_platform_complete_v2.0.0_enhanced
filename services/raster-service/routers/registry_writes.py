"""routers/registry_writes.py — أوامرُ الكتابة المملوكة: كتالوجُ الراستر وطابورُ الإبطال (D1).

``raster_registry`` و``raster_cache_invalidations`` جدولان يملكهما ``raster-service``
(`docs/architecture/db_ownership.yml`)، وكانت ``sahool-platform`` تكتبهما بـSQL مباشر
(``/cog-registry`` و``spatial_sync.mark_raster_cache_stale``) — كاتبان لجدولٍ واحد
(`db_writer_ownership_triage.json`: ``dual-writer``). هذا الراوتر هو **واجهةُ الكتابة
التي يملكها المالك**: المنصّة تبقى مُنتِجةً/منسِّقةً وتُرسل أمراً؛ الخدمةُ وحدَها تلمس
الجدول.

العقد (كلا المسارين):
  • ``X-Agent-Token`` توكنُ خدمةٍ إلزاميّ (``require_service_token``) — لا مسارَ متصفّح.
  • المستأجِر من رأس البوّابة الموثوق ``X-Tenant-Id`` (``REQ_TENANT``) حصراً؛ ``tenant_id``
    في الجسم يُقبَل مطابقاً ويُرفض مخالفاً (403) — النمطُ نفسُه في ``routers/fields.py``.
  • الحقلُ يجب أن يكون مرئيّاً ومملوكاً للمستأجِر (``fields`` عبر ``sahool_field_owner_tenant``):
    مجهولٌ ⇒ 404، لمستأجِرٍ آخر ⇒ 403 — الأوامرُ تصل بعد التزام كتابة الحقل في المنصّة.
  • الإدراجُ idempotent: مفتاحُ v114 الفريد للكتالوج، و``request_id`` (فحصٌ قبل الإدراج؛
    الفهرسُ الفريد له هجرةٌ على مسارٍ مجمَّد تحتاج تفويضَ المالك — حدٌّ مُعلَن) لطابور الإبطال.
  • بلا ``DATABASE_URL`` أو بقاعدةٍ متعذّرة ⇒ 503 صريح؛ لا نجاحَ مُختلَق.
"""

from __future__ import annotations

from typing import Any

import db_persist
import raster_security_context
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

_REQUEST_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"


class CacheInvalidationCommand(BaseModel):
    """أمرُ إبطالٍ لحقل: السبب + مفتاحُ الطلب (idempotency) + بياناتٌ حرّة (مثل geometry_revision)."""

    tenant_id: str | None = None
    reason: str = Field(min_length=1, max_length=200)
    request_id: str = Field(min_length=1, max_length=128, pattern=_REQUEST_ID_PATTERN)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CogRegistryCommand(BaseModel):
    """أمرُ تسجيل COG في الكتالوج — الحقولُ نفسُها التي كانت المنصّة تُدرجها مباشرةً."""

    tenant_id: str | None = None
    field_id: str = Field(min_length=1, max_length=50)
    scene_id: str | None = None
    product_date: str = Field(min_length=10, max_length=40)
    index_type: str = Field(min_length=1, max_length=64)
    cog_url: str = Field(min_length=1)
    cloud_pct: float | None = 0
    quality_score: int | None = Field(default=None, ge=0, le=100)
    resolution_m: float = 10
    bbox: list[float] | dict[str, Any] | None = None
    bands: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _authenticated_tenant(body_tenant: str | None) -> str:
    """المستأجِر من سياق الطلب الموثوق — الجسمُ لا يتجاوزه، وغيابُه يحجب.

    ``routers/fields.py::_authenticated_tenant`` يُعيد ``None`` عند غياب السياق لأنّ
    مساراتِه تُكمِل فحصَ الملكيّة لاحقاً؛ أمرُ كتابةٍ مملوك بلا مستأجِر لا معنى له ولا
    يُدرَج شيءٌ تحت مستأجِرٍ فارغ (RLS كان سيقبله بـ``WITH CHECK`` حين يكون السياق فارغاً).
    """
    context_tenant = raster_security_context.REQ_TENANT.get()
    if not context_tenant:
        raise HTTPException(403, "X-Tenant-Id مطلوب لأمر كتابةٍ يملكه raster-service")
    if body_tenant is not None and str(body_tenant) != str(context_tenant):
        raise HTTPException(403, "tenant_id في الجسم لا يطابق المستأجِر المُصادَق للطلب")
    return str(context_tenant)


async def _require_field_owned_by(field_id: str, tenant: str) -> None:
    """الحقلُ يجب أن يكون **مرئيّاً ومملوكاً** للمستأجِر المُصادَق — صارمٌ لا «عند الإثبات فقط».

    الأوامرُ تصل **بعد التزام** كتابة الحقل في المنصّة (مُوصِّلٌ بعد COMMIT)، فالحقلُ مرئيّ
    لـ``sahool_field_owner_tenant`` وقتَ الأمر: مجهولٌ ⇒ 404 (لا إدراجَ لمعرّفٍ وهميّ تحت
    أيّ مستأجِر)، لمستأجِرٍ آخر ⇒ 403، تعذُّرُ الإثبات ⇒ 503 (fail-closed). الكاشُ السالب
    في ``field_owner`` (15ث) قد يُخفي حقلاً التُزم للتوّ — فـ404 عند المُوصِّل قابلةٌ
    لإعادة المحاولة لا نهائيّة.
    """
    try:
        owner = await raster_security_context.field_owner(field_id)
    except db_persist.OwnerLookupUnavailable as e:
        raise HTTPException(503, "تعذّر إثبات ملكيّة الحقل — أعد المحاولة لاحقاً") from e
    if not owner:
        raise HTTPException(404, "الحقل غير موجود أو غير مرئيّ بعد")
    if str(owner) != tenant:
        raise HTTPException(403, "الحقل لا يخصّ مستأجِرك")


def _require_database() -> None:
    if not db_persist.DATABASE_URL:
        raise HTTPException(503, "DATABASE_URL غير مضبوط — أوامرُ الكتابة المملوكة معطّلة بأمان")


def _validate_identity(field_id: str, tenant: str) -> None:
    if not db_persist._valid_field_id_text(field_id):
        raise HTTPException(400, "field_id غير صالح (محارف آمنة، حتّى 50)")
    if not db_persist._valid_uuid_text(tenant):
        raise HTTPException(400, "المستأجِر المُصادَق ليس UUID")


@router.post("/v1/fields/{field_id}/cache-invalidations", status_code=202)
async def enqueue_field_cache_invalidation(
    field_id: str,
    body: CacheInvalidationCommand,
    x_agent_token: str | None = Header(None),
) -> dict:
    """يُدرج طلبَ إبطالٍ لحقلٍ في طابور ``raster_cache_invalidations`` (المستهلك: العامل).

    202: قُبِل وأُدرج (``deduplicated=false``) أو كان قائماً بمفتاح الطلب نفسِه
    (``deduplicated=true``). الاستجابةُ تعيد صفَّ الطابور (id/status/created_at) كي يقرأ
    المُرسِل الحالةَ الحقيقيّة لا افتراضاً.
    """
    raster_security_context.require_service_token(x_agent_token)
    tenant = _authenticated_tenant(body.tenant_id)
    _validate_identity(field_id, tenant)
    _require_database()
    await _require_field_owned_by(field_id, tenant)
    result = await db_persist.enqueue_cache_invalidation(
        tenant_id=tenant,
        field_id=field_id,
        reason=body.reason,
        request_id=body.request_id,
        metadata=body.metadata,
    )
    if result is None:
        raise HTTPException(503, "تعذّر تسجيل الإبطال في الطابور — أعد المحاولة لاحقاً")
    return {
        "accepted": True,
        "field_id": field_id,
        "tenant_id": tenant,
        "request_id": body.request_id,
        "deduplicated": bool(result.get("deduplicated")),
        "invalidation": {
            "id": result.get("id"),
            "status": result.get("status"),
            "created_at": result.get("created_at"),
        },
    }


@router.post("/v1/registry/cogs")
async def register_cog_entry(
    body: CogRegistryCommand,
    x_agent_token: str | None = Header(None),
) -> dict:
    """يُدرج/يحدّث صفَّ كتالوج ``raster_registry`` ويُعيده (``entry``) — المنصّة تبني منه STAC.

    ``field_id`` إلزاميّ: مفتاحُ v114 الفريد يشمله، وصفٌّ بلا حقل لا يُزال تكرارُه أبداً
    (NULL لا يساوي NULL) — المسارُ القديم كان يقبل غيابَه ويُنتِج صفوفاً مكرَّرة صامتة.
    """
    raster_security_context.require_service_token(x_agent_token)
    tenant = _authenticated_tenant(body.tenant_id)
    _validate_identity(body.field_id, tenant)
    _require_database()
    await _require_field_owned_by(body.field_id, tenant)
    entry = await db_persist.upsert_raster_registry_entry(
        tenant_id=tenant,
        field_id=body.field_id,
        scene_id=body.scene_id,
        product_date=body.product_date,
        index_type=body.index_type,
        cog_url=body.cog_url,
        cloud_pct=body.cloud_pct,
        quality_score=body.quality_score,
        resolution_m=body.resolution_m,
        bbox=body.bbox,
        bands=body.bands,
        metadata=body.metadata,
    )
    if entry is None:
        raise HTTPException(503, "تعذّر تسجيل صفّ الكتالوج — أعد المحاولة لاحقاً")
    return {"registered": True, "entry": entry}
