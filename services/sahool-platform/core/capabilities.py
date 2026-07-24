"""capabilities.py — بوّابة القدرات المشروطة (conditional deferred capabilities).

كل قدرة "مؤجَّلة" (FCM/ML/مستقبِلات التنبيه) مبنيّة بكودها الحقيقي لكن مُسوَّرة
بشرط تفعيل (متغيّر بيئة / ملفّ نموذج / سرّ). دون الشرط تبقى خاملة بصدق
(no-op / fallback مُعلَن — لا اختراع بيانات)؛ بتحقّق الشرط يبدأ تدفّق بياناتها
الحقيقي فوراً دون تعديل كود. (التوقّع الجوّي الحيّ Open-Meteo ليس مؤجَّلاً —
keyless ومربوط افتراضيّاً في weather_forecast_adapter، فليس ضمن هذه البوّابة.)

مبدأ: القدرة حاضرة، خاملة حتى التزويد. (capability present, dormant until provisioned)

كل خدمة (notification/edge-inference/weather) تقرأ نفس أسماء المتغيّرات هنا
لتقرّر التفعيل؛ وهذه الوحدة تُجمِّع الحالة لنقطة /api/v1/capabilities (شفافيّة).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _truthy(v: str | None) -> bool:
    return bool(v and v.strip() and v.strip().lower() not in ("0", "false", "no", "off"))


def _file_present(env_key: str) -> bool:
    p = os.getenv(env_key, "")
    return bool(p) and os.path.exists(p)


# ─── شروط التفعيل (تُقرأ في الخدمات المعنيّة بنفس الأسماء) ──────────


def fcm_push_active() -> bool:
    """إشعارات Push تُفعَّل عند ضبط FCM_SERVER_KEY (مسار FCM legacy المُنفَّذ فعلاً).

    ملاحظة (مراجعة): لا نعتبر FCM_CREDENTIALS_JSON كافياً — مسار HTTP v1 (حساب
    الخدمة) غير مربوط في notification-agent بعد، فاعتباره "مُفعَّلاً" يجعل
    /capabilities يكذب (active بينما الإرسال يُرجِع False). يُوسَّع الشرط عند ربط v1.
    """
    return _truthy(os.getenv("FCM_SERVER_KEY"))


# ملاحظة: التنبّؤ الجوّي الحيّ (Open-Meteo) ليس قدرةً مؤجَّلة — Open-Meteo مجّاني
# بلا مفتاح، فهو مربوط كمصدر افتراضيّ في weather_forecast_adapter (يُحاوَل دائماً،
# ويسقط بصدق إلى None عند تعذّر الشبكة). الانسحاب للنشر المعزول: WEATHER_LIVE_DISABLED.


def ml_pest_active() -> bool:
    """كشف الآفات بنموذج ML — يتطلّب ملفّ ONNX موجوداً."""
    return _file_present("PEST_MODEL_PATH")


def ml_yield_active() -> bool:
    """تنبّؤ الإنتاج بنموذج ML — يتطلّب ملفّ ONNX موجوداً."""
    return _file_present("YIELD_MODEL_PATH")


def alerting_receivers_active() -> bool:
    """مستقبِلات تنبيه حقيقيّة (Slack/email/Telegram) عبر تراكب النشر."""
    return any(
        _truthy(os.getenv(k))
        for k in ("ALERT_SLACK_WEBHOOK", "ALERT_SMTP_HOST", "ALERT_TELEGRAM_TOKEN")
    )


def ml_field_boundary_active() -> bool:
    """كشف حدود الحقل بنموذج حقيقيّ — backend غير حتميّ + أوزان FTW مُزوَّدة (نفس أسماء
    متغيّرات ``ai_agronomist/field_boundary_backends.py``). دون ذلك يسقط للاستدلال الحتميّ."""
    backend = os.getenv("SAHOOL_FIELD_BOUNDARY_BACKEND", "deterministic").strip().lower()
    return backend not in ("", "deterministic") and _truthy(os.getenv("SAHOOL_FTW_WEIGHTS"))


def aquacrop_salinity_active() -> bool:
    """محرّك AquaCrop لإجهاد الملوحة — راية ``AQUACROP_ENABLED`` (نفس اسم
    ``agriai-engine/aquacrop_adapter.py``). دون التفعيل: نموذج عتبيّ ساكن موسوم uncalibrated."""
    return _truthy(os.getenv("AQUACROP_ENABLED"))


# ملاحظة صدق (لا نُدرِج قدرتين هنا لأنّهما ليستا «مشروطتين ببيئة»، فإدراجهما يكذب على السجلّ):
#   • مناطق الإنتاجيّة (productivity_zones): **حتميّة دائماً** (لا وضع «نموذج حقيقيّ» يُبوَّب عليه)
#     — طرقها كلّها `*_fallback` موسومة في الحمولة؛ ليست قدرة مؤجَّلة.
#   • WOFOST: مُبوَّبة بحضور وحدة المحرّك وقت التشغيل (importlib) لا بمتغيّر بيئة — تعبيرها هنا
#     بمتغيّر مُخمَّن سيكون غير دقيق؛ نقطة /simulate تُعلن available=false بصدق عند غيابها.


@dataclass
class Capability:
    key: str
    name_ar: str
    active: bool
    activation_ar: str  # كيف تُفعَّل (تعليمات تشغيليّة)
    fallback_ar: str  # السلوك الخامل الصادق


def all_capabilities() -> list[Capability]:
    """سجلّ القدرات المشروطة + حالتها الحاليّة (للنقطة وللتشخيص)."""
    return [
        Capability(
            "fcm_push",
            "إشعارات Push (FCM/APNs)",
            fcm_push_active(),
            "عيّن FCM_SERVER_KEY (مسار FCM legacy؛ HTTP v1/JSON يُربط لاحقاً)",
            "لا إرسال Push (البريد/تلغرام/داخل-التطبيق تعمل)؛ لا إشعار وهميّ",
        ),
        Capability(
            "ml_pest_detection",
            "كشف الآفات بنموذج ML",
            ml_pest_active(),
            "ضع نموذج ONNX وعيّن PEST_MODEL_PATH على مساره",
            "يسقط للتشخيص القاعديّ بالأعراض (مُعلَن، لا نموذج مزيّف)",
        ),
        Capability(
            "ml_yield_prediction",
            "تنبّؤ الإنتاج بنموذج ML",
            ml_yield_active(),
            "ضع نموذج ONNX وعيّن YIELD_MODEL_PATH على مساره",
            "يسقط للتقدير القاعديّ الاستدلاليّ (مُعلَن)",
        ),
        Capability(
            "alerting_receivers",
            "مستقبِلات التنبيه (Slack/email/Telegram)",
            alerting_receivers_active(),
            "عيّن ALERT_SLACK_WEBHOOK أو ALERT_SMTP_HOST أو ALERT_TELEGRAM_TOKEN",
            "AlertManager يستقبل لكنّه لا يُسلّم (no-op، لا ضجيج)",
        ),
        Capability(
            "ml_field_boundary",
            "كشف حدود الحقل بنموذج ML (FTW/SAM)",
            ml_field_boundary_active(),
            "عيّن SAHOOL_FIELD_BOUNDARY_BACKEND=ftw وزوّد SAHOOL_FTW_WEIGHTS بمسار الأوزان",
            "استدلال حتميّ (bbox/تتبّع كنتور مؤشّر) موسوم method في الحمولة — لا نموذج مزيّف",
        ),
        Capability(
            "aquacrop_salinity",
            "محرّك AquaCrop لإجهاد الملوحة",
            aquacrop_salinity_active(),
            "عيّن AQUACROP_ENABLED=1 (يتطلّب حزمة aquacrop الحقيقيّة)",
            "نموذج ملوحة عتبيّ ساكن (Maas-Hoffman) موسوم aquacrop_uncalibrated — لا نقل زمنيّ مُختلَق",
        ),
    ]


def capabilities_report() -> dict:
    caps = all_capabilities()
    return {
        "capabilities": [
            {
                "key": c.key,
                "name_ar": c.name_ar,
                "status": "active" if c.active else "dormant",
                "activation_ar": c.activation_ar,
                "fallback_ar": c.fallback_ar,
            }
            for c in caps
        ],
        "active_count": sum(1 for c in caps if c.active),
        "dormant_count": sum(1 for c in caps if not c.active),
        "note_ar": "القدرات الخاملة حاضرة في الكود وتبدأ فور تحقّق شرطها — لا تعديل لازم",
    }
