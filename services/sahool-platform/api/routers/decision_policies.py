"""api/routers/decision_policies.py — سجلّ سياسات القرار (المرحلة B، الشريحة 5).

يُسطِّح سجلّ سياسات الحوكمة (`core.policy_registry` + جدول decision_policies) عبر نقاط
محروسة بعلم `SAHOOL_DECISION_DISPATCH` (مُطفأ افتراضاً ⇒ 404؛ نفس بوّابة موزِّع القرار):

  • `POST …/decision/policies`   — إنشاء سياسة (نطاق→أثر) للمستأجِر.
  • `GET  …/decision/policies`   — سرد سياسات المستأجِر (معزولة بـRLS).
  • `POST …/decision/policies/resolve` — استشارة نقيّة (dry-run): أيّ أثر حوكمة ينطبق
    على سياق (action_type/risk_level/crop)؟ تُغذّي مسار القرار الموحّد/الموزِّع.

الصدق: الاستشارة نقيّة (لا كتابة)؛ السياسات تكمّل الحواجز ولا تستبدلها (auto_block غالب
تحفّظاً). معزولة بـRLS لكلّ مستأجِر. التطبيق الحيّ في مسار القرار شريحة لاحقة موصولة.
"""

from __future__ import annotations

import json as _json
import os
import uuid as _uuid

from core.policy_registry import Policy, resolve_policies
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}


def _dispatch_enabled() -> bool:
    """نفس بوّابة موزِّع القرار (إنضاج تدريجيّ موحّد للحلقة)."""
    return os.getenv("SAHOOL_DECISION_DISPATCH", "").strip().lower() in _TRUTHY


def _require_enabled() -> None:
    if not _dispatch_enabled():
        raise HTTPException(
            status_code=404, detail="ميزة موزِّع القرار غير مُفعَّلة (اضبط SAHOOL_DECISION_DISPATCH)."
        )


def _shape_policy_row(row) -> dict:
    """يحوّل صفّ decision_policies إلى dict عرض — يفكّ JSONB ويُنسّق الوقت (نقيّ)."""

    def _loads(v):
        if v is None:
            return None
        return _json.loads(v) if isinstance(v, str) else v

    created = row["created_at"]
    return {
        "policy_id": row["policy_id"],
        "name": row["name"],
        "scope": _loads(row["scope"]),
        "effect": _loads(row["effect"]),
        "priority": row["priority"],
        "enabled": row["enabled"],
        "created_by": row["created_by"],
        "created_at": created.isoformat() if created is not None else None,
    }


class PolicyCreateRequest(BaseModel):
    """مدخلات إنشاء سياسة: اسم + نطاق + أثر + أولويّة/تفعيل."""

    name: str
    scope: dict = {}  # {action_type?, risk_level?, crop?}
    effect: dict = {}  # {auto_block?, require_approvals?, water_cap_pct?}
    priority: int = 0
    enabled: bool = True


@router.post("/api/v1/decision/policies")
async def create_policy(
    req: PolicyCreateRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_REQUEST)),
) -> dict:
    """ينشئ سياسة حوكمة للمستأجِر (معزولة بـRLS). 404 إن مُطفأ، 503 عند تعذّر القاعدة."""
    _require_enabled()
    policy_id = "pol_" + _uuid.uuid4().hex[:16]
    try:
        async with tenant_connection(user) as conn:
            await conn.execute(
                """INSERT INTO decision_policies
                    (policy_id, tenant_id, name, scope, effect, priority, enabled, created_by)
                   VALUES ($1, $2::uuid, $3, $4::jsonb, $5::jsonb, $6, $7, $8)""",
                policy_id,
                str(user.tenant_id),
                req.name,
                _json.dumps(req.scope),
                _json.dumps(req.effect),
                req.priority,
                req.enabled,
                str(user.user_id),
            )
            row = await conn.fetchrow(
                "SELECT * FROM decision_policies WHERE policy_id = $1", policy_id
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إنشاء سياسة القرار", e) from e
    return _shape_policy_row(row)


@router.get("/api/v1/decision/policies")
async def list_policies(
    enabled_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """يسرد سياسات المستأجِر (الأعلى أولويّة أوّلاً) — معزول بـRLS، خلف العلم."""
    _require_enabled()
    try:
        async with tenant_connection(user) as conn:
            if enabled_only:
                rows = await conn.fetch(
                    "SELECT * FROM decision_policies WHERE enabled = TRUE "
                    "ORDER BY priority DESC, created_at DESC LIMIT $1",
                    limit,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM decision_policies "
                    "ORDER BY priority DESC, created_at DESC LIMIT $1",
                    limit,
                )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سياسات القرار", e) from e
    return {"policies": [_shape_policy_row(r) for r in rows], "count": len(rows)}


class PolicyResolveRequest(BaseModel):
    """مدخلات استشارة السجلّ: سياق القرار (نطاق) لاستخلاص الأثر المُجمَّع."""

    action_type: str | None = None
    risk_level: str | None = None
    crop: str | None = None


@router.post("/api/v1/decision/policies/resolve")
async def resolve_policy_endpoint(
    req: PolicyResolveRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """استشارة نقيّة (dry-run): أيّ أثر حوكمة ينطبق على السياق؟ — يُغذّي مسار القرار.

    يقرأ سياسات المستأجِر المُفعّلة (RLS) ويُجمِّع أثرها عبر core.policy_registry (تحفّظيّ:
    auto_block غالب، أقصى موافقات، أدنى سقف ماء). لا كتابة. 404 إن مُطفأ، 503 عند تعذّر القاعدة.
    """
    _require_enabled()
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT * FROM decision_policies WHERE enabled = TRUE ORDER BY priority DESC"
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("استشارة سياسات القرار", e) from e

    def _loads(v):
        return _json.loads(v) if isinstance(v, str) else (v or {})

    policies = [
        Policy(
            policy_id=r["policy_id"],
            name=r["name"],
            scope=_loads(r["scope"]),
            effect=_loads(r["effect"]),
            priority=r["priority"],
            enabled=r["enabled"],
        )
        for r in rows
    ]
    context = {"action_type": req.action_type, "risk_level": req.risk_level, "crop": req.crop}
    resolved = resolve_policies(policies, context)
    out = resolved.to_dict()
    out["context"] = context
    out["dry_run"] = True
    return out
