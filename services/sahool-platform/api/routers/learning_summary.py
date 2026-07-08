"""api/routers/learning_summary.py — نقطة تلخيص حلقة التعلّم (Learning Dashboard data)

تُغلق رأس عرض حلقة التعلّم: لوحة الرصد تحتاج لقطةً مُجمَّعة لحالة الحلقة المُدامة
(Decision→Outcome→Evidence). محروسة بعلم `FEATURE_LEARNING_DASHBOARD` (مُطفأ افتراضاً ⇒ 404؛
نمط الإغلاق المرن — إنضاج تدريجيّ).

  • `GET /api/v1/learning/summary` — لقطة مُجمَّعة لحالة حلقة التعلّم للمستأجِر.

P4.6 read-side facade: هذا الموجِّه لم يعد يقرأ جداول القرار/النتيجة/التعلّم مباشرةً؛
يُفوّض القراءة إلى decision-service (الخدمة المالكة لدلالات المُصالحة) عبر واجهة
`api.decision_service_client`. تبقى المصادقة/الصلاحيّة (`require_permission`) والإغلاق
المرن (العلم ⇒ 404) في المنصّة. المنطق النقيّ للتجميع/المُصالحة محفوظ في
`api.learning_summary`/`core.outcome_reconciler` (مُختبَر وحدويّاً) ويُستهلَك في مسارات
قراءة أخرى (موسم الحقل)، وسيُوصَل داخل الخدمة المالكة.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    UserSchema,
    require_permission,
)

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}


def _learning_dashboard_enabled() -> bool:
    """هل لوحة رصد حلقة التعلّم مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ، إغلاق مرن)."""
    return os.getenv("FEATURE_LEARNING_DASHBOARD", "").strip().lower() in _TRUTHY


@router.get("/api/v1/learning/summary")
async def get_learning_summary(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """يُجمِّع حالة حلقة التعلّم المُدامة للوحة الرصد — قراءة فقط.

    P4.6 read-side facade: المنصّة لم تعد تقرأ جداول القرار/النتيجة/التعلّم مباشرةً لهذه
    اللوحة؛ تُمرّر سياق المستأجِر إلى decision-service التي تملك دلالات المُصالحة (المنطق
    النقيّ للتجميع/المُصالحة محفوظ في ``api.learning_summary``/``core.outcome_reconciler``
    ويُستهلَك في مسارات قراءة أخرى — موسم الحقل — وسيُوصَل داخل الخدمة المالكة).
    404 إن كان العلم مُطفأ (إغلاق مرن). تبقى المصادقة/الصلاحيّة في المنصّة.
    """
    if not _learning_dashboard_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة لوحة حلقة التعلّم غير مُفعَّلة (اضبط FEATURE_LEARNING_DASHBOARD).",
        )
    from api.decision_service_client import (
        get_learning_summary as _get_learning_summary_via_service,
    )

    summary = await _get_learning_summary_via_service(tenant_id=str(user.tenant_id))
    if isinstance(summary, dict):
        # تنسيق أيّ طوابع زمنيّة تعيدها الخدمة إلى ISO (حدود I/O) — لا منطق تجميع هنا.
        _isoformat_stamps(summary)
    return summary


_STAMP_KEYS = ("last_decision_at", "last_outcome_at", "last_activity_at")


def _isoformat_stamps(summary: dict) -> None:
    """ينسّق طوابع كلّ منطقة + الإجماليّ إلى ISO (datetime ⇒ str) في المكان — لا منطق تجميع.

    التجميع النقيّ (summarize_learning) يمرّر created_at كما وَرَد (datetime من asyncpg)؛
    نُنسّقه هنا في طبقة الموجِّه (حدود I/O) لإبقاء منطق التجميع حتميّاً بلا اعتماد نوعٍ زمنيّ.
    """

    def _iso(snap: dict) -> None:
        for k in _STAMP_KEYS:
            v = snap.get(k)
            if v is not None and hasattr(v, "isoformat"):
                snap[k] = v.isoformat()

    for region_snap in summary.get("regions", []):
        _iso(region_snap)
    if summary.get("overall"):
        _iso(summary["overall"])
