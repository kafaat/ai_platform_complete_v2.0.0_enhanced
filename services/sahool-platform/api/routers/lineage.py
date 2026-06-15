"""api/routers/lineage.py — نسب الكيان الكامل (Lineage / data_lineage)
===============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: المسار/الأذونات/المخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

``LineageAssembler`` صارت يتيمة الاستخدام في ``main`` بعد النقل فتُستورَد هنا من
وحدتها الحقيقيّة ``api.data_lineage`` مباشرةً (إزالة F401). لتفادي الاستيراد الدائريّ:
``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

# LineageAssembler تُستورَد مباشرةً من وحدتها الحقيقيّة (نفس الرمز الذي كان main
# يستورده) لإزالة F401 من main بعد نقل هذه الدالّة.
from api.data_lineage import LineageAssembler
from api.main import (
    UserSchema,
    get_current_user,
    get_pool,
    tenant_connection,
)

router = APIRouter()


@router.get("/api/v1/lineage/{entity_type}/{entity_id}")
async def entity_lineage(
    entity_type: str,
    entity_id: str,
    limit: int = 500,
    user: UserSchema = Depends(get_current_user),
):
    """يجمع lineage كامل للـentity (command+event+lifecycle+journal+trueup).

    عبر tenant_connection — RLS مُطبَّق (لا تسريب عبر المستأجرين)."""
    async with tenant_connection(user) as conn:
        assembler = LineageAssembler(get_pool(), conn=conn)
        result = await assembler.get_entity_lineage(entity_type, entity_id, limit=limit)
    return {
        "entity_type": result.entity_type,
        "entity_id": result.entity_id,
        "total_entries": result.total_entries,
        "earliest_at": result.earliest_at,
        "latest_at": result.latest_at,
        "commands_count": result.commands_count,
        "events_count": result.events_count,
        "entries": [
            {
                "timestamp": e.timestamp,
                "source_type": e.source_type.value,
                "source_id": e.source_id,
                "action": e.action,
                "summary_ar": e.summary_ar,
            }
            for e in result.entries
        ],
    }
