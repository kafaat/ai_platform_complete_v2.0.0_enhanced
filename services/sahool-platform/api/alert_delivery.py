"""api/alert_delivery.py — توجيه التنبيهات إلى قنوات الإشعار (منطق صرف، pure).

خارطة الطريق: Sprint — قنوات تسليم التنبيهات. يقرّر — بناءً على تفضيلات
المستخدم (notification_preferences) ونوع/خطورة التنبيه — أيّ القنوات تستحقّ
هذا التنبيه، ويُصيّر نصّاً عربيّاً مناسباً لكلّ قناة.

المبدأ:
  • هذا المنطق **نقيّ** (لا شبكة، لا قاعدة، لا I/O) — يُختبَر offline بالكامل.
  • النواة (main.py) تقرأ صفّ التفضيلات من القاعدة، تبني NotificationPrefs،
    وتمرّره مع التنبيه إلى select_channels؛ ثمّ تُسجّل (log) نيّة التسليم.
  • الإرسال الفعليّ (SMS/بريد/Push/واتساب) ليس هنا: لا توجد بوّابة حقيقيّة في
    هذه البيئة. select_channels يُنتج رسائل ChannelMessage جاهزة للإرسال؛ مُرسِل
    حقيقيّ (ChannelSender) يُوصَّل لاحقاً عبر deliver() بلا تغيير هذا المنطق.

⚠ أرضيّة الخطورة (severity floor) لكلّ قناة heuristic منتجيّ مبسّط: القنوات
الأغلى/الأكثر إزعاجاً (SMS/واتساب) لا تتلقّى إلّا الخطورة العالية افتراضيّاً،
بينما البريد/Push يتلقّيان كلّ شيء. قابلة للضبط لكلّ مستخدم لاحقاً.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

# ─── ترتيب الخطورة (severity) — لمقارنة الأرضيّة لكلّ قناة ───────────
# يطابق _ALERT_SEVERITIES في main.py: info < warning < critical.
SEVERITY_ORDER: dict[str, int] = {"info": 0, "warning": 1, "critical": 2}

# القنوات المدعومة. telegram موجود في الجدول القديم لكن واجهة هذا السبرنت
# تعرض: بريد/SMS/Push/واتساب. نُبقي telegram ضمن القنوات لكي لا نكسر بيانات
# قائمة، لكنّ select_channels يعتمد فقط الأعلام المُمرَّرة في التفضيلات.
CHANNEL_EMAIL = "email"
CHANNEL_SMS = "sms"
CHANNEL_PUSH = "push"
CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_TELEGRAM = "telegram"

# ─── أرضيّة الخطورة الافتراضيّة لكلّ قناة ────────────────────────────
# القناة لا تتلقّى تنبيهاً أدنى من أرضيّتها. SMS/واتساب: 'critical' فقط
# (مكلفة/مزعجة) — هذا ما طلبته خارطة الطريق صراحةً. بريد/Push: من 'info'.
DEFAULT_SEVERITY_FLOOR: dict[str, str] = {
    CHANNEL_EMAIL: "info",
    CHANNEL_PUSH: "info",
    CHANNEL_TELEGRAM: "warning",
    CHANNEL_WHATSAPP: "critical",
    CHANNEL_SMS: "critical",
}

# ترجمة عربيّة لدرجة الخطورة — للعنوان/الرسالة المُصيَّرة.
_SEVERITY_AR: dict[str, str] = {
    "info": "معلومة",
    "warning": "تحذير",
    "critical": "حرِج",
}


@dataclass(frozen=True)
class NotificationPrefs:
    """تفضيلات إشعار مستخدم — مرآة صفّ notification_preferences (القنوات + العناوين
    + أنواع الأحداث المُشترَك بها). كلّها اختياريّة بقيم آمنة افتراضيّة (مُعطَّلة).

    event_types: قائمة أنواع الأحداث المُختارة. None ⇒ بلا ترشيح بالنوع (الكلّ
    مسموح)؛ قائمة (حتى الفارغة) ⇒ يُرسَل فقط ما نوعه ضمنها.
    """

    email_enabled: bool = False
    email_address: str | None = None
    sms_enabled: bool = False
    sms_number: str | None = None
    push_enabled: bool = False
    push_token: str | None = None
    whatsapp_enabled: bool = False
    whatsapp_number: str | None = None
    event_types: list[str] | None = None
    # أرضيّة خطورة دنيا عامّة للمستخدم (تُطبَّق فوق أرضيّة القناة الافتراضيّة).
    # None ⇒ تُستخدم أرضيّة القناة الافتراضيّة فقط.
    min_severity: str | None = None


@dataclass(frozen=True)
class AlertInput:
    """التنبيه كما يحتاجه التوجيه — نوع/خطورة/نصّ عربيّ (مرآة AlertSummary)."""

    alert_type: str
    severity: str
    title_ar: str | None = None
    message_ar: str | None = None
    field_id: str | None = None


@dataclass(frozen=True)
class ChannelMessage:
    """رسالة جاهزة لقناة واحدة — ناتج التوجيه. مُرسِل حقيقيّ يستهلكها لاحقاً.

    recipient: العنوان/الرقم/الرمز للقناة (بريد/هاتف/token). قد يكون None لو لم
    يضبطه المستخدم — التوجيه يُبلِّغ عنه (deliverable=False) بدل ابتلاعه بصمت.
    """

    channel: str
    severity: str
    recipient: str | None
    title_ar: str
    body_ar: str

    @property
    def deliverable(self) -> bool:
        """جاهزة للإرسال فعليّاً؟ (القناة مُفعَّلة ولها عنوان صالح)."""
        return bool(self.recipient and self.recipient.strip())


def _severity_rank(severity: str) -> int:
    """رتبة الخطورة (غير المعروفة تُعامَل كأدنى رتبة — لا تتجاوز أرضيّة)."""
    return SEVERITY_ORDER.get(severity, 0)


def _passes_event_filter(prefs: NotificationPrefs, alert: AlertInput) -> bool:
    """هل نوع التنبيه ضمن أنواع الأحداث المُشترَك بها؟ (None ⇒ بلا ترشيح)."""
    if prefs.event_types is None:
        return True
    return alert.alert_type in prefs.event_types


def _passes_severity_floor(channel: str, alert: AlertInput, prefs: NotificationPrefs) -> bool:
    """هل خطورة التنبيه ≥ أرضيّة القناة (وأرضيّة المستخدم العامّة إن وُجدت)؟"""
    floor = DEFAULT_SEVERITY_FLOOR.get(channel, "info")
    floor_rank = _severity_rank(floor)
    if prefs.min_severity is not None:
        floor_rank = max(floor_rank, _severity_rank(prefs.min_severity))
    return _severity_rank(alert.severity) >= floor_rank


def _render_body(channel: str, alert: AlertInput) -> tuple[str, str]:
    """يُصيّر (العنوان، النصّ) العربيّ لقناة — مُختصَر للقنوات النصّيّة القصيرة.

    SMS/واتساب: نصّ قصير (سطر واحد) لتقليل الكلفة. بريد/Push: نصّ أوفى.
    """
    sev_ar = _SEVERITY_AR.get(alert.severity, alert.severity)
    title = alert.title_ar or f"تنبيه زراعيّ ({sev_ar})"
    detail = (alert.message_ar or "").strip()

    if channel in (CHANNEL_SMS, CHANNEL_WHATSAPP):
        # سطر واحد مُوجَز: [خطورة] العنوان — النصّ (إن وُجد).
        line = f"[{sev_ar}] {title}"
        if detail:
            line = f"{line} — {detail}"
        return title, line

    # بريد/Push/تلغرام: عنوان + متن.
    body = f"درجة الخطورة: {sev_ar}\n{title}"
    if detail:
        body = f"{body}\n\n{detail}"
    return title, body


# خريطة القناة → (هل مُفعَّلة؟، المُستقبِل) من التفضيلات — مصدر واحد للحقيقة.
def _channel_targets(
    prefs: NotificationPrefs,
) -> list[tuple[str, bool, str | None]]:
    return [
        (CHANNEL_EMAIL, prefs.email_enabled, prefs.email_address),
        (CHANNEL_SMS, prefs.sms_enabled, prefs.sms_number),
        (CHANNEL_PUSH, prefs.push_enabled, prefs.push_token),
        (CHANNEL_WHATSAPP, prefs.whatsapp_enabled, prefs.whatsapp_number),
    ]


def select_channels(prefs: NotificationPrefs, alert: AlertInput) -> list[ChannelMessage]:
    """يقرّر أيّ القنوات تتلقّى هذا التنبيه ويُصيّر رسالة عربيّة لكلّ منها.

    قناة تُختار فقط إذا: (1) مُفعَّلة في التفضيلات، (2) نوع التنبيه ضمن أنواع
    الأحداث المُشترَك بها، (3) خطورة التنبيه ≥ أرضيّة القناة (+ أرضيّة المستخدم).
    العنوان غير المضبوط لا يمنع الاختيار لكن يُعلَّم deliverable=False ليُسجَّل
    بصدق (المُستخدم فعّل قناة بلا عنوان). الترتيب ثابت (ترتيب القنوات أعلاه).
    """
    if not _passes_event_filter(prefs, alert):
        return []

    out: list[ChannelMessage] = []
    for channel, enabled, recipient in _channel_targets(prefs):
        if not enabled:
            continue
        if not _passes_severity_floor(channel, alert, prefs):
            continue
        title, body = _render_body(channel, alert)
        out.append(
            ChannelMessage(
                channel=channel,
                severity=alert.severity,
                recipient=recipient,
                title_ar=title,
                body_ar=body,
            )
        )
    return out


# ─── مُرسِل قابل للتوصيل (sender plug point) ─────────────────────────
# الإرسال الحقيقيّ غير متاح هنا (لا بوّابة SMS/بريد). نُعرّف بروتوكول مُرسِل +
# مُرسِل افتراضيّ يُسجّل فقط (StubSender)، فيستطيع كودٌ منتجيّ لاحقاً تمرير
# مُرسِل حقيقيّ (Twilio/SES/FCM/WhatsApp Cloud API) دون تغيير select_channels.

# نتيجة محاولة تسليم واحدة: (القناة، نجَح؟، تفصيل). تُسجَّل/تُخزَّن في النواة.
DeliveryResult = tuple[str, bool, str]

# توقيع المُرسِل: يأخذ ChannelMessage ويُعيد DeliveryResult.
ChannelSender = Callable[[ChannelMessage], DeliveryResult]


def stub_sender(msg: ChannelMessage) -> DeliveryResult:
    """مُرسِل وهميّ (لا I/O): لا يُرسِل فعليّاً — يُبلِّغ بصدق عن النيّة فقط.

    قناة بلا عنوان ⇒ فشل صريح (لا ابتلاع). قناة بعنوان ⇒ 'مُسجَّل' (logged) لا
    'مُرسَل' — لا نزعم إرسالاً لم يحدث. استبدله بمُرسِل حقيقيّ عبر deliver().
    """
    if not msg.deliverable:
        return (msg.channel, False, "لا عنوان مضبوط لهذه القناة")
    return (msg.channel, True, "مُسجَّل (لا إرسال فعليّ — بيئة بلا بوّابة)")


@dataclass
class DeliveryPlan:
    """خطّة تسليم تنبيه: الرسائل المُختارة + نتائج محاولات التسليم (إن نُفِّذت)."""

    messages: list[ChannelMessage] = field(default_factory=list)
    results: list[DeliveryResult] = field(default_factory=list)

    @property
    def deliverable_count(self) -> int:
        return sum(1 for m in self.messages if m.deliverable)


def plan_delivery(prefs: NotificationPrefs, alert: AlertInput) -> DeliveryPlan:
    """يبني خطّة تسليم (اختيار القنوات فقط، بلا إرسال) — نقطة دخول النواة."""
    return DeliveryPlan(messages=select_channels(prefs, alert))


def deliver(
    prefs: NotificationPrefs,
    alert: AlertInput,
    sender: ChannelSender = stub_sender,
) -> DeliveryPlan:
    """يختار القنوات ثمّ يُمرّر كلّ رسالة للمُرسِل (الافتراضيّ stub) ويجمع النتائج.

    نقيّ بالنسبة للاختيار؛ أيّ أثر جانبيّ يقع داخل sender المُمرَّر (قابل للحقن
    في الاختبار). النواة تستدعيه بـstub_sender وتُسجّل النتائج (لا إرسال فعليّ).
    """
    plan = plan_delivery(prefs, alert)
    plan.results = [sender(m) for m in plan.messages]
    return plan
