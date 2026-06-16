"""api/alert_models.py — نماذج وثوابت ومُطبِّع طبقة التنبيهات الزراعيّة — تفكيك B1.

الطبقة النقيّة من «محرّك التنبيهات» المُستخرَجة من الوحدة الضخمة ``api/main.py``:
ثوابت التصنيف (أنواع/خطورة/حالة) + نماذج Pydantic (إنشاء/ملخّص/استجابة تقييم) +
مُطبِّع الصفّ (DB→نموذج). **منطق نماذج صرف** (pydantic + stdlib فقط) بلا I/O وبلا
أيّ تبعيّة على ``api.main`` — فتُستورَد من ``routers/alerts``/``notifications``/
``reports``/``fields`` والاختبارات مباشرةً، وتستوردها ``api.main`` لمستهلِكيها
الداخليّين (``_row_to_alert`` في مُشكِّل لوحة المؤشّرات، و``AlertSummary`` في
محرّك التوليد ``_evaluate_field_alerts_persist``).

يبقى محرّك التوليد/التسليم (``_evaluate_field_alerts_persist``/``_log_alert_deliveries``)
في ``api.main``: I/O على القاعدة + اقتران بطبقة تفضيلات الإشعار + استدعاء داخليّ من
جدولة الأتمتة — فلا يُنقَل مع الطبقة النقيّة.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ─── التنبيهات الزراعيّة (Alerts) — نمط activities (v36) ──────────
_ALERT_TYPES = {
    "low_moisture",
    "heavy_rain",
    "disease_risk",
    "heat_stress",
    "frost_risk",
    "other",
}
_ALERT_SEVERITIES = {"info", "warning", "critical"}
_ALERT_STATUSES = {"active", "acknowledged", "resolved"}


class AlertCreateRequest(BaseModel):
    """طلب إنشاء تنبيه زراعيّ (نوع/خطورة/عنوان/نصّ/حقل اختياريّ)."""

    alert_type: str
    severity: str
    title_ar: str | None = Field(default=None, max_length=200)
    message_ar: str | None = None
    field_id: str | None = None


class AlertSummary(BaseModel):
    alert_id: str
    field_id: str | None = None
    alert_type: str
    severity: str
    title_ar: str | None = None
    message_ar: str | None = None
    status: str
    created_at: str | None = None


def _row_to_alert(r) -> AlertSummary:
    return AlertSummary(
        alert_id=r["alert_id"],
        field_id=r["field_id"],
        alert_type=r["alert_type"],
        severity=r["severity"],
        title_ar=r["title_ar"],
        message_ar=r["message_ar"],
        status=r["status"],
        created_at=r["created_at"].isoformat() if r["created_at"] else None,
    )


class AlertEvaluateResponse(BaseModel):
    """ناتج تقييم تنبيهات حقل: المُنشأ + عدد المُتجاوَز (موجود نشط مسبقاً)."""

    created: list[AlertSummary]
    skipped_existing: int
