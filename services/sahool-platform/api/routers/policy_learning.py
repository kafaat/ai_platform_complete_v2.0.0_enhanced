"""api/routers/policy_learning.py — حلقة تعلّم السياسة (Policy Learning).

شريحة موجِّه (APIRouter) على نمط P0 — تقرأ **نتائج** التنبيهات المُسجَّلة لكلّ
مستأجِر وتُرجع اقتراحات ضبط عتبات التنبيه (core.policy_learning، منطق نقيّ).

مصدر الإشارة الحقيقيّ: جدول ``alerts`` (status ∈ active/acknowledged/resolved)؛
نطابق ``status ∈ {acknowledged, resolved} ⇒ useful=True`` و``active ⇒ useful=False``
(راجع docstring core.policy_learning للمبرّر الكامل). الإذن: ANALYTICS_VIEW (قراءة
تحليليّة فقط — مطابقة لبقيّة نقاط التحليلات). 503 عند تعذّر القاعدة.

⚠ لا تكتب الإعدادات: تُرجع **اقتراحات** فقط (human-in-the-loop). لا تُطبَّق آليّاً.
الموجِّه لا يُسجَّل في main.py هنا — القائد يربطه (نمط P0).
"""

from __future__ import annotations

from core.policy_learning import derive_threshold_adjustments
from fastapi import APIRouter, Depends

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()

# حالات تدلّ على تفاعُل المستأجِر مع التنبيه ⇒ إشارة «نافع».
_USEFUL_STATUSES = ("acknowledged", "resolved")
# سقف أمان للقراءة (تجنّب over-fetch على تاريخ تنبيهات طويل).
_MAX_OUTCOMES = 5000


@router.get("/api/v1/policy-learning/threshold-suggestions")
async def threshold_suggestions(
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    """يُرجع اقتراحات ضبط عتبات التنبيه لكلّ مستأجِر من نتائجه المُسجَّلة.

    يقرأ حالات تنبيهات المستأجِر (alerts) — مُرشَّحة بالمستأجِر (RLS) — ويطابقها إلى
    ``{alert_type, useful}`` (تفاعُل المستأجِر = نافع)، ثمّ يستدعي المنطق النقيّ
    ``derive_threshold_adjustments``. لا نتائج ⇒ نتيجة صادقة فارغة (per_type={}).
    503 عند تعذّر القاعدة. لا يكتب أيّ إعداد — اقتراحات human-in-the-loop فقط.
    """
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT alert_type, status FROM alerts "
                "WHERE tenant_id = $1::uuid "
                "ORDER BY created_at DESC LIMIT $2",
                str(getattr(user, "tenant_id", "")),
                _MAX_OUTCOMES,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة نتائج التنبيهات لاشتقاق اقتراحات السياسة", e) from e

    # تطابق الإشارة الحقيقيّ: تفاعُل المستأجِر (acknowledged/resolved) = نافع.
    outcomes = [
        {
            "alert_type": r["alert_type"],
            "useful": r["status"] in _USEFUL_STATUSES,
        }
        for r in rows
    ]
    suggestions = derive_threshold_adjustments(outcomes)
    suggestions["outcomes_considered"] = len(outcomes)
    return suggestions
