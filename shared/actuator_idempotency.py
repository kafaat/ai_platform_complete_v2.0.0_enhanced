"""shared/actuator_idempotency.py — منطق إزالة التكرار العنقوديّ للـactuator (نقيّ حتميّ).

المشكلة (تدقيق الأنظمة الموزّعة): حارس التكرار في actuator-service كان dict داخل العمليّة
(_dedup_last_fired) — per-replica لا عنقوديّ. مع عدّة نُسَخ/إعادة تسليم MQTT/إعادة تشغيل،
قد يُطلَق الأمر مرّةً لكلّ نسخة ⇒ **تنفيذ مزدوج على مضخّة/صمّام** (أخطر فجوة ميدانيّة).

الحلّ بنمط **الإغلاق المرن** (Introduce → Observe → Enforce) — لا استبدال صلب:
  • local   (افتراضيّ): السلوك الحاليّ تماماً (داخل العمليّة فقط) — صفر تغيير/مخاطرة.
  • shadow  : المخزن العنقوديّ (DB) يُستشار ويُرصَد، لكنّ **المحلّيّ يقرّر** — مرحلة مراقبة
              نقيس فيها التباين (هل العنقوديّ كان سيمنع تكراراً فاتَ المحلّيّ؟).
  • cluster : المخزن العنقوديّ **يحسم** (cluster-safe)؛ وعند تعذّره ⇒ **fail-soft** للمحلّيّ.

هذا الملفّ **نقيّ تماماً**: لا قاعدة ولا شبكة — منطق دمج القرار فقط (الفحص العنقوديّ
الذرّيّ نفسه يجري في الموجِّه عبر القاعدة). فيُختبَر حتميّاً بلا بنية تحتيّة.
"""

from __future__ import annotations

_MODES = ("local", "shadow", "cluster")


def resolve_idempotency_mode(raw: str | None) -> str:
    """يطبّع وضع الـidempotency من البيئة. أيّ قيمة مجهولة ⇒ local (الأكثر تحفّظاً).

    local: داخل العمليّة فقط (السلوك الحاليّ). shadow: محلّيّ يقرّر + عنقوديّ يُرصَد.
    cluster: عنقوديّ يحسم (fail-soft للمحلّيّ عند تعذّر المخزن).
    """
    v = (raw or "").strip().lower()
    return v if v in _MODES else "local"


def decide_fire(
    mode: str,
    local_fire: bool,
    cluster_fire: bool,
    cluster_available: bool,
) -> tuple[bool, str]:
    """يدمج قرار الـdedup المحلّيّ والعنقوديّ حسب الوضع ⇒ (يُطلَق؟، مفتاح المقياس) — نقيّ.

    - cluster + متاح        ⇒ العنقوديّ يحسم (cluster-safe، يمنع التنفيذ المزدوج).
    - cluster + غير متاح    ⇒ fail-soft: يرجع للمحلّيّ (لا نوقف الفعل الميدانيّ كلّيّاً).
    - shadow                ⇒ المحلّيّ يحسم؛ نرصد التباين (divergence) لقياس قيمة الترقية.
    - local                 ⇒ المحلّيّ فقط (السلوك الحاليّ).

    مفتاح المقياس يُمكّن المراقبة (Observe) قبل الفرض (Enforce): تباين/رجوع/تخطٍّ عنقوديّ.
    """
    if mode == "cluster":
        if cluster_available:
            return cluster_fire, ("cluster_fire" if cluster_fire else "cluster_skip")
        return local_fire, "cluster_unavailable_fallback"  # fail-soft
    if mode == "shadow":
        if cluster_available:
            if local_fire != cluster_fire:
                return local_fire, "shadow_divergence"  # العنقوديّ كان سيقرّر غير المحلّيّ
            return local_fire, "shadow_agree"
        return local_fire, "shadow_store_unavailable"
    return local_fire, "local"


# أسماء العدّادات المعتمدة (شروط القبول) — مصدر واحد للحقيقة كي تتطابق المقاييس والاختبارات.
METRIC_LOCAL_HIT = "idempotency_local_hit"
METRIC_CLUSTER_HIT = "idempotency_cluster_hit"
METRIC_SHADOW_DIVERGENCE = "idempotency_shadow_divergence"
METRIC_CLUSTER_UNAVAILABLE = "idempotency_cluster_unavailable"
METRIC_DUPLICATE_BLOCKED = "actuator_command_duplicate_blocked"


def idempotency_counters(
    mode: str,
    local_fire: bool,
    cluster_fire: bool,
    cluster_available: bool,
    fire: bool,
) -> tuple[str, ...]:
    """يُعيد أسماء العدّادات الواجب رفعها لهذا القرار — نقيّ حتميّ (مواءمة شروط القبول).

    العدّادات المعتمدة (تُرصَد قبل الفرض):
      • idempotency_local_hit         — المحلّيّ التقط تكراراً (قراره: لا تُطلِق) — أيّ وضع.
      • idempotency_cluster_hit       — العنقوديّ (متاح) التقط تكراراً — shadow/cluster.
      • idempotency_shadow_divergence — في shadow اختلف المحلّيّ والعنقوديّ. **معيار الانتقال**:
        يجب أن يبلغ صفراً عبر N أيّام/أوامر قبل تفعيل cluster.
      • idempotency_cluster_unavailable — في cluster تعذّر المخزن (حدث fail-soft للمحلّيّ).
      • actuator_command_duplicate_blocked — القرار النهائيّ منع تكراراً (المقياس القابل للتنفيذ).

    صدق: local لا يلمس عدّادات العنقود (مَحروسة بالوضع)؛ فالافتراض يبقى صفر-تأثير.
    """
    out: list[str] = []
    if not local_fire:
        out.append(METRIC_LOCAL_HIT)
    if mode in ("shadow", "cluster") and cluster_available and not cluster_fire:
        out.append(METRIC_CLUSTER_HIT)
    if mode == "shadow" and cluster_available and local_fire != cluster_fire:
        out.append(METRIC_SHADOW_DIVERGENCE)
    if mode == "cluster" and not cluster_available:
        out.append(METRIC_CLUSTER_UNAVAILABLE)
    if not fire:
        out.append(METRIC_DUPLICATE_BLOCKED)
    return tuple(out)
