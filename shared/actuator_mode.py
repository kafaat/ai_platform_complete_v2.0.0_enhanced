"""shared/actuator_mode.py — أوضاع المُشغِّل (actuator) النقيّة الحتميّة (PR #394).

المشكلة الميدانيّة: عند **غياب وسيط FastBee** (broker)، يفشل نشر MQTT صامتاً ⇒ تنقطع
سلسلة الأتمتة (command → execution_ledger → ack) فلا يُسجَّل تنفيذ ولا أثر. هذا يُعمي
المراقبة ويُعطّل اختبار التدفّق دون بنية MQTT حيّة.

الحلّ بنمط **الإغلاق المرن** (لا كسر للسلوك الحاليّ) عبر علم `ACTUATOR_MODE`:
  • real        : ينشر MQTT فعليّاً (السلوك الحاليّ عند توفّر وسيط).
  • simulation  : **لا ينشر**؛ يُعيد نجاحاً محاكى موسوماً (simulated=true) ويُسجِّل log —
                  فتبقى السلسلة كاملة (command → ledger → simulated_ack) بلا وسيط حقيقيّ.
                  صدق صريح: يُعلن أنّه محاكاة ولا يدّعي تنفيذاً فيزيائيّاً.
  • disabled    : لا عمليّة (يُعيد فشلاً/تخطّياً كالسلوك الحاليّ عند غياب الوسيط).

هذا الملفّ **نقيّ تماماً**: لا قاعدة ولا شبكة — منطق اشتقاق الوضع فقط، فيُختبَر حتميّاً
بلا بنية تحتيّة. الافتراضيّ يحفظ السلوك الحاليّ تماماً (يُستنتج من MQTT_BROKER_URL).
"""

from __future__ import annotations

_MODES = ("real", "simulation", "disabled")


def _broker_implies_disabled(broker_url: str | None) -> bool:
    """يطابق `_mqtt_disabled` في الخدمة: لا عنوان أو يبدأ بـ'disabled' ⇒ معطّل."""
    url = (broker_url or "").strip()
    return not url or url.startswith("disabled")


def resolve_actuator_mode(raw: str | None, broker_url: str | None) -> str:
    """يطبّع وضع المُشغِّل من البيئة، مع **حفظ السلوك الحاليّ** عند غياب العلم.

    - علم صريح صالح (real/simulation/disabled، غير حسّاس للحالة) ⇒ يُحترَم كما هو.
    - علم غائب/فارغ/مجهول ⇒ **يُستنتَج من `broker_url`** (السلوك الحاليّ تماماً):
        • عنوان فارغ أو يبدأ بـ'disabled' ⇒ "disabled".
        • وإلّا ⇒ "real".

    دالّة نقيّة حتميّة (لا بيئة ولا قاعدة) ليُختبَر الاشتقاق وحدويّاً.
    """
    v = (raw or "").strip().lower()
    if v in _MODES:
        return v
    # لا علم صريح ⇒ استنتج من الوسيط (يحفظ السلوك الحاليّ بالضبط).
    return "disabled" if _broker_implies_disabled(broker_url) else "real"
