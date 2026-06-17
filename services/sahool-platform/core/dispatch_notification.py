"""core/dispatch_notification.py — مستهلِك الموزِّع: ترجمة قرار مُدرَج إلى إخطار بشريّ (نقيّ).

إغلاق الحلقة بأمان (المرحلة A، الشريحة 3). القرار المُخلَّص يُدرَج في الطابور
(exec_status='queued')؛ من يستهلكه؟ المبدأ التشغيليّ الصريح: **نبدأ بالبشر لا بالمضخّات**
— المستهلِك الأوّل يترجم القرار إلى إخطار (SMS / واتساب / مهمّة تطبيق) يصل المزارع/الفنّيّ
ليُنفّذ يدويّاً، لا أمر MQTT أعمى لصمّام. هذا يُغلِق الحلقة (قرار→تنفيذ) بوسيط بشريّ
قابل للمساءلة قبل أيّ أتمتة فيزيائيّة لاحقة.

نقيّة وحتميّة (لا I/O، لا إرسال): تأخذ صفّ قرار + قناة، تُرجِع **حمولة إخطار** جاهزة
يستهلكها مُسلِّم القنوات القائم (core.alert_delivery) أو يُدرَجها في صفّ المهام. الصدق:
لا تدّعي إرسالاً — تبني الحمولة فقط؛ التسليم الفعليّ طبقة لاحقة (قناة مُهيّأة). تعيين
exec_status='dispatched' يعني «سُلِّم للمستهلِك/أُخطِر»، لا «نُفِّذ» (ذاك في السجلّ، الشريحة 4).
"""

from __future__ import annotations

from typing import Any

# القنوات المدعومة للمستهلِك البشريّ (مرآة لقنوات core.alert_delivery القائمة).
CHANNELS = ("sms", "whatsapp", "mobile_task")
_DEFAULT_CHANNEL = "mobile_task"

# عناوين عربيّة موجزة لكلّ نوع إجراء (يقرؤها الفنّيّ/المزارع على الهاتف).
_ACTION_TITLE_AR = {
    "irrigation": "إجراء ريّ مطلوب",
    "defer_irrigation": "تأجيل ريّ مطلوب",
    "spray": "إجراء رشّ مطلوب",
    "fertilize": "إجراء تسميد مطلوب",
    "reduce_water": "خفض كمّيّة الماء",
}

# إلحاح الإخطار من مستوى مخاطر القرار (مرآة لشدّة التنبيهات info/warning/critical).
_RISK_SEVERITY = {"LOW": "info", "MEDIUM": "warning", "HIGH": "critical", "CRITICAL": "critical"}


def normalize_channel(channel: str | None) -> str:
    """يُطبّع القناة إلى واحدة مدعومة — مجهول/غائب ⇒ mobile_task (الأقلّ كلفة وأماناً)."""
    c = (channel or "").strip().lower()
    return c if c in CHANNELS else _DEFAULT_CHANNEL


def build_dispatch_notification(decision_row: Any, channel: str | None = None) -> dict:
    """يترجم صفّ قرار مُدرَج (queued) إلى حمولة إخطار بشريّ (نقيّ، لا إرسال).

    `decision_row`: قاموس/سجلّ بمفاتيح dispatch_decisions (decision_id, action_type,
    field_id, risk_level, reason_ar, command). يُرجِع حمولة موحّدة يستهلكها مُسلِّم
    القنوات (alert_delivery) أو صفّ المهام. الصدق: حمولة فقط — التسليم طبقة لاحقة.
    """

    def _get(key, default=None):
        try:
            return decision_row[key]
        except (KeyError, TypeError, IndexError):
            return getattr(decision_row, key, default)

    action = (_get("action_type") or "").strip()
    field_id = _get("field_id")
    risk = (_get("risk_level") or "").strip().upper()
    reason = _get("reason_ar") or ""
    decision_id = _get("decision_id")
    command = _get("command")

    title = _ACTION_TITLE_AR.get(action, "إجراء زراعيّ مطلوب")
    severity = _RISK_SEVERITY.get(risk, "warning")
    field_part = f" — الحقل {field_id}" if field_id else ""
    body = (reason or title) + field_part

    return {
        "channel": normalize_channel(channel),
        "severity": severity,
        "decision_id": decision_id,
        "action_type": action,
        "field_id": field_id,
        "title_ar": title,
        "body_ar": body,
        "command": command,  # سياق للفنّيّ (الجهاز/الأمر المقترح) — لا إطلاق آليّ
        "requires_human_action": True,  # صدق: إخطار لتنفيذ يدويّ، لا أتمتة فيزيائيّة
    }
