"""api/fleet_health.py — مراقبة صحّة أسطول الأجهزة الطرفيّة (إنذار استباقي).

الفكرة (مُستلهَمة من مبدأ MDM "الإنذار المبكر / وداعاً للمراقبة العمياء"،
لا من أداة Sunflower): بدل أن يكتشف المزارع صمت جهاز بالصدفة عند فتح القائمة،
يُحسب **استباقيّاً** أيّ جهاز صامت، ويُميَّز حسب **حرجيّته** (حسّاس رطوبة في
حقل نشط ≠ كاميرا اختياريّة)، ويُلخَّص كـ"صحّة أسطول".

ما يبنيه (الفجوة المسدودة):
  • iot_devices.last_seen_at موجود + GET /devices يحسب online ✓ (لكن pull فقط)
  • صمت الأجهزة **ليس** ضمن alert_rules ✗ — لا إنذار استباقي
  • لا تمييز خطورة حسب نوع/دور الجهاز ✗

⚠ المبدأ:
  • حتمي بالكامل: عتبات صمت صريحة حسب نوع الجهاز (لا نموذج، لا اختراع)
  • تمييز الخطورة: الجهاز الحرج (يغذّي قراراً نشطاً) صمته أخطر
  • لكلّ مستأجر (سيادة البيانات) — RLS يحكم الاستعلام
  • يُكمّل لا يستبدل: GET /devices للعرض، هذا للإنذار الاستباقي

⚠ ليس تحكّماً عن بُعد بالأجهزة (خارج نطاق سهول الأمني). مراقبة صحّة فقط.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DeviceCriticality(str, Enum):
    """حرجيّة الجهاز — تحدّد خطورة صمته."""

    CRITICAL = "critical"  # يغذّي قراراً نشطاً (رطوبة/عدّاد ماء لحقل مزروع)
    IMPORTANT = "important"  # مهمّ لكن غير فوري (محطّة طقس، مُشغّل)
    OPTIONAL = "optional"  # اختياري (كاميرا، other)


# عتبات الصمت (دقائق) حسب نوع الجهاز — كم يصمت قبل اعتباره مفقوداً.
# المنطق: حسّاس الرطوبة يُرسل كثيراً (صمت 30د مقلق)؛ الطقس أبطأ (3 ساعات).
SILENCE_THRESHOLDS_MIN: dict[str, int] = {
    "soil_moisture": 30,  # يُرسل دوريّاً — صمت 30د = خلل
    "water_meter": 60,  # عدّاد الماء — صمت ساعة مقلق
    "actuator": 60,  # المُشغّل — يجب أن يستجيب
    "weather_station": 180,  # الطقس أبطأ تحديثاً
    "camera": 360,  # الكاميرا اختياريّة
    "other": 240,
}

# حرجيّة كلّ نوع (الأساس — تُرفَع إن كان الجهاز مرتبطاً بحقل نشط)
TYPE_CRITICALITY: dict[str, DeviceCriticality] = {
    "soil_moisture": DeviceCriticality.CRITICAL,
    "water_meter": DeviceCriticality.CRITICAL,
    "actuator": DeviceCriticality.IMPORTANT,
    "weather_station": DeviceCriticality.IMPORTANT,
    "camera": DeviceCriticality.OPTIONAL,
    "other": DeviceCriticality.OPTIONAL,
}


@dataclass
class DeviceHealthRecord:
    """سجلّ صحّة جهاز (يُبنى من صفّ iot_devices + حساب الصمت)."""

    device_id: str
    name: str
    device_type: str
    field_id: str | None
    minutes_since_seen: float | None  # None = لم يُرَ قطّ


def assess_device(rec: DeviceHealthRecord, field_is_active: bool = False) -> dict:
    """يقيّم صحّة جهاز واحد: صامت؟ ما خطورة صمته؟ (حتمي).

    field_is_active: هل الحقل المرتبط في موسم نشط؟ يرفع الحرجيّة.
    """
    threshold = SILENCE_THRESHOLDS_MIN.get(rec.device_type, 240)
    base_crit = TYPE_CRITICALITY.get(rec.device_type, DeviceCriticality.OPTIONAL)

    # never seen أو تجاوز العتبة = صامت
    if rec.minutes_since_seen is None:
        silent = True
        detail = "لم يُرسل أيّ بيانات قطّ (لم يُفعَّل أو معطّل)"
    elif rec.minutes_since_seen > threshold:
        silent = True
        detail = (
            f"صامت منذ {int(rec.minutes_since_seen)} دقيقة "
            f"(العتبة {threshold} د لنوع {rec.device_type})"
        )
    else:
        silent = False
        detail = f"نشط (آخر ظهور قبل {int(rec.minutes_since_seen)} د)"

    # رفع الحرجيّة إن كان جهازاً حرجاً في حقل نشط
    crit = base_crit
    if silent and field_is_active and base_crit == DeviceCriticality.CRITICAL:
        crit_note = "⚠ حرج: حقل نشط يعتمد هذا الجهاز لقرار الريّ"
    elif silent and base_crit == DeviceCriticality.CRITICAL:
        crit_note = "جهاز حرج صامت (الحقل غير نشط حاليّاً)"
    elif silent:
        crit_note = f"صمت {base_crit.value} — أقلّ إلحاحاً"
    else:
        crit_note = ""

    return {
        "device_id": rec.device_id,
        "name": rec.name,
        "type": rec.device_type,
        "field_id": rec.field_id,
        "silent": silent,
        "criticality": crit.value,
        "detail_ar": detail,
        "criticality_note_ar": crit_note,
        "threshold_minutes": threshold,
    }


def assess_fleet(
    records: list[DeviceHealthRecord], active_field_ids: set[str] | None = None
) -> dict:
    """صحّة الأسطول الكاملة: ملخّص + الأجهزة الصامتة مرتّبة بالخطورة.

    active_field_ids: الحقول في مواسم نشطة (لرفع حرجيّة أجهزتها).
    """
    active = active_field_ids or set()
    assessed = [
        assess_device(r, field_is_active=(r.field_id in active if r.field_id else False))
        for r in records
    ]
    silent = [a for a in assessed if a["silent"]]
    # ترتيب الصامتة: الحرجة أوّلاً
    crit_rank = {"critical": 0, "important": 1, "optional": 2}
    silent.sort(key=lambda a: crit_rank.get(a["criticality"], 3))

    critical_silent = [a for a in silent if a["criticality"] == "critical"]

    return {
        "total_devices": len(records),
        "online": len(records) - len(silent),
        "silent": len(silent),
        "critical_silent": len(critical_silent),
        "fleet_status_ar": (
            "🟢 الأسطول سليم — كلّ الأجهزة نشطة"
            if not silent
            else f"🔴 {len(critical_silent)} جهاز حرج صامت — يحتاج تدخّلاً عاجلاً"
            if critical_silent
            else f"🟡 {len(silent)} جهاز صامت (غير حرج) — راجع عند الإمكان"
        ),
        "silent_devices": silent,  # مرتّبة بالخطورة
        "proactive_note_ar": (
            "كشف استباقي: يُحسب صمت الأجهزة دوريّاً ويُنبّه قبل أن يكتشفه المزارع "
            "بالصدفة. الحرجيّة تُرفَع للأجهزة التي يعتمدها قرار نشط."
        ),
        "honesty_note_ar": (
            "مراقبة صحّة فقط (حتميّة من last_seen). لا تحكّم عن بُعد بالأجهزة. "
            "العتبات تقديريّة حسب نوع الجهاز — تُضبط بالخبرة الميدانيّة."
        ),
    }
