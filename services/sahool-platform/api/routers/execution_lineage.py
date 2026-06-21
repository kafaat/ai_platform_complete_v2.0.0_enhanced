"""api/routers/execution_lineage.py — توحيد نَسَب التنفيذ (Unified Execution Lineage, PR #396).

يُسطِّح جسر الربط (`api.execution_lineage`) عبر نقطتين، محروستين بعلم
`FEATURE_UNIFIED_LINEAGE` (مُطفأ افتراضاً ⇒ 404؛ إنضاج تدريجيّ كنمط decision_dispatch):

  • `POST …/lineage/link` — يُدِيم رابطاً بين معرّف عالميّ موحّد (lin_) ومرجع قائم
    (decision/dispatch/command/execution/outcome) **دون إعادة تسمية المرجع** — القديم
    يستمر، الجديد يربط فوقه. ON CONFLICT DO NOTHING (كلّ مرجع يُربَط مرّةً)، يُصدِر حدثاً.
  • `GET …/lineage/{lineage_id}` — يُعيد كلّ روابط السلسلة لذلك المعرّف (معزول RLS).

الصدق: الربط إضافيّ خلف علم — لا يكسر السلوك القائم؛ لا يُعاد تسمية dec_/disp_/command_id.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.execution_lineage import lineage_link_row
from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    _emit_domain_event,
    require_permission,
    tenant_connection,
)

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}


def _lineage_enabled() -> bool:
    """هل ميزة النَّسَب الموحّد مُفعَّلة؟ (مُطفأة افتراضاً — إغلاق مرن، إنضاج تدريجيّ)."""
    return os.getenv("FEATURE_UNIFIED_LINEAGE", "").strip().lower() in _TRUTHY


def _shape_link_row(row) -> dict:
    """يحوّل صفّ lineage_link إلى dict عرض — يُنسّق الوقت (نقيّ)."""
    created = row["created_at"]
    return {
        "lineage_id": row["lineage_id"],
        "ref_type": row["ref_type"],
        "ref_id": row["ref_id"],
        "created_at": created.isoformat() if created is not None else None,
    }


class LineageLinkRequest(BaseModel):
    """مدخلات ربط مرجع بسلسلة نَسَب: lineage_id اختياريّ (يُسَكّ إن غاب) + نوع/معرّف المرجع."""

    ref_type: str  # decision | dispatch | command | execution | outcome (مجهول ⇒ 400)
    ref_id: str
    lineage_id: str | None = None  # يُعاد استخدامه إن مُرِّر، وإلّا يُسَكّ معرّف عالميّ جديد


@router.post("/api/v1/lineage/link")
async def link_lineage_ref(
    req: LineageLinkRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
) -> dict:
    """يربط مرجعاً قائماً (dec_/disp_/command_id/…) بمعرّف نَسَب عالميّ موحّد (lin_).

    404 إن كانت الميزة مُطفأة. الربط إضافيّ فوق المعرّفات القائمة (لا إعادة تسمية). يُسَكّ
    lineage_id إن غاب. ON CONFLICT (tenant,ref_type,ref_id) DO NOTHING ⇒ ربط آمن متكرّر
    (idempotent). يُصدِر LINEAGE_LINKED عبر outbox. 400 لنوع مرجع مجهول، 503 عند تعذّر القاعدة.
    """
    if not _lineage_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة النَّسَب الموحّد غير مُفعَّلة (اضبط FEATURE_UNIFIED_LINEAGE).",
        )
    try:
        link = lineage_link_row(req.lineage_id, req.ref_type, req.ref_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        async with tenant_connection(user) as conn:
            # كلّ مرجع يُربَط مرّةً (UNIQUE tenant,ref_type,ref_id) — ربط متكرّر آمن.
            await conn.execute(
                """INSERT INTO lineage_link (lineage_id, tenant_id, ref_type, ref_id)
                   VALUES ($1, $2::uuid, $3, $4)
                   ON CONFLICT (tenant_id, ref_type, ref_id) DO NOTHING""",
                link["lineage_id"],
                str(user.tenant_id),
                link["ref_type"],
                link["ref_id"],
            )
            # تدقيق: حدث domain عبر outbox ضمن المعاملة (best-effort داخل _emit).
            await _emit_domain_event(
                conn,
                user,
                "LINEAGE_LINKED",
                "lineage_link",
                link["lineage_id"],
                {
                    "lineage_id": link["lineage_id"],
                    "ref_type": link["ref_type"],
                    "ref_id": link["ref_id"],
                },
                critical=True,  # سلامة سلسلة المساءلة — fail-closed
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إدامة رابط النَّسَب", e) from e

    return {
        "lineage_id": link["lineage_id"],
        "ref_type": link["ref_type"],
        "ref_id": link["ref_id"],
        "linked_by": str(user.user_id),
    }


@router.get("/api/v1/lineage/{lineage_id}")
async def get_lineage_chain(
    lineage_id: str,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """يُعيد كلّ روابط سلسلة نَسَب لمعرّف عالميّ موحّد (lin_) — معزول RLS، خلف العلم.

    قراءة فقط: يجمع decision/dispatch/command/execution/outcome المربوطة بذلك lineage_id.
    404 إن مُطفأ. 503 عند تعذّر القاعدة. سلسلة فارغة تُعاد كقائمة فارغة (لا اختراع).
    """
    if not _lineage_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة النَّسَب الموحّد غير مُفعَّلة (اضبط FEATURE_UNIFIED_LINEAGE).",
        )
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT * FROM lineage_link WHERE lineage_id = $1 "
                "ORDER BY ref_type ASC, created_at ASC",
                lineage_id,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سلسلة النَّسَب", e) from e
    return {
        "lineage_id": lineage_id,
        "links": [_shape_link_row(r) for r in rows],
        "count": len(rows),
    }
