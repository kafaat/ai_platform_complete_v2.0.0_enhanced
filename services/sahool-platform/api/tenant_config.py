"""
api/tenant_config.py — تكوين المستأجِر (Tenant Configuration) — #13

يتيح لكلّ مستأجِر تخصيص هويّته البصريّة (الشعار/الألوان/الاسم) ووحداته
(المساحة/الحرارة) ولغته ومحاصيله **دون أيّ تعديل برمجيّ** — التخصيص بيانات لا
كود. يُخزَّن في جدول `settings` القائم (لا جدول جديد، لا ترحيل) تحت:

    scope = 'platform'  ,  key = 'tenant_config'  ,  value = <تكوين جزئيّ JSONB>

⚠ الكتابة تمرّ عبر النقطة القائمة `PUT /api/v1/settings` (بصلاحيّة SETTINGS_MANAGE):

    PUT /api/v1/settings
    { "scope": "platform", "key": "tenant_config", "value": { ... جزئيّ ... } }

لا نضيف نقطة كتابة جديدة. القراءة الفعّالة عبر `GET /api/v1/tenant/config` التي
تستدعي `merge_tenant_config` لتركيب ما خزّنه المستأجِر فوق القيم المحايدة
الافتراضيّة (overlay). القيم المخزّنة **جزئيّة**: يكفي المستأجِر أن يحدّد ما يريد
تغييره، والباقي يبقى على الافتراضات.

الدوالّ هنا **نقيّة** (لا قاعدة بيانات، لا شبكة، لا تستثني أبداً) — قابلة للاختبار
offline. الوصول للقاعدة يبقى في `main.py` ضمن `tenant_connection` (RLS).
"""

from __future__ import annotations

import copy

# ─── الافتراضات المحايدة (DEFAULTS) ──────────────────────────────
# قيم محايدة تطابق السلوك الضمنيّ الحاليّ للمنصّة قبل التخصيص. أيّ مستأجِر لم
# يحفظ تكويناً يرى هذه القيم بالضبط.
DEFAULTS: dict = {
    # الهويّة البصريّة (Branding) — ما يظهر في الواجهة لهذا المستأجِر.
    "branding": {
        "logo_url": None,  # لا شعار افتراضيّ — الواجهة تعرض الاسم النصّيّ حين None.
        "primary_color": "#2e7d32",  # أخضر سهول الزراعيّ — لون المنصّة الحاليّ.
        "name_ar": "سهول",  # الاسم العربيّ الافتراضيّ للمنصّة.
    },
    # الوحدات (Units) — وحدات العرض الضمنيّة الحاليّة في المنصّة.
    "units": {
        "area": "hectare",  # المساحة بالهكتار (area_ha هي وحدة الجداول الحاليّة).
        "temperature": "celsius",  # الحرارة بالمئويّة (وحدة الطقس الحاليّة).
    },
    # اللغة (Language) — العربيّة هي لغة المنصّة الأمّ (كلّ النصوص _ar).
    "language": "ar",
    # المحاصيل (Crops) — قائمة محاصيل المستأجِر المُفضّلة؛ فارغة افتراضاً
    # (لا تقييد — المستأجِر يضيف محاصيله إن رغب بتخصيص القوائم).
    "crops": [],
}

# المفاتيح العليا المعروفة فقط — أيّ مفتاح آخر في المُدخل يُتجاهَل (تجاهل آمن).
_KNOWN_TOP_KEYS = frozenset(DEFAULTS.keys())
# المفاتيح الفرعيّة المعروفة داخل القواميس المتداخلة (branding/units).
_KNOWN_SUB_KEYS: dict[str, frozenset[str]] = {
    "branding": frozenset(DEFAULTS["branding"].keys()),
    "units": frozenset(DEFAULTS["units"].keys()),
}


def merge_tenant_config(raw: dict | None) -> dict:
    """يُركّب تكويناً جزئيّاً مخزَّناً فوق الافتراضات المحايدة (overlay) ويُرجِع
    التكوين **الفعّال** الكامل.

    الدمج عميق للمفاتيح المعروفة فقط (branding/units/language/crops)، ويدمج داخل
    branding/units المفاتيح الفرعيّة المعروفة فقط. أيّ مفتاح غير معروف — علويّ أو
    فرعيّ — يُتجاهَل بأمان. المُدخل المُشوَّه أو None يُرجِع نسخة من الافتراضات.

    دالّة نقيّة لا تستثني أبداً: تُستدعى على قيمة JSONB قد تكون None أو من نوع
    غير متوقَّع، فتتصرّف دفاعيّاً وتُرجِع دائماً تكويناً صالحاً.

    المستأجِر يضبط هذا عبر `PUT /api/v1/settings`
    (scope='platform', key='tenant_config', value=<تكوين جزئيّ>)، وهذه الدالّة
    تركّبه فوق الافتراضات المحايدة.
    """
    # ابدأ دائماً من نسخة عميقة مستقلّة من الافتراضات (لا نطفر الأصل أبداً).
    merged = copy.deepcopy(DEFAULTS)

    # مُدخل مُشوَّه/غائب ⇒ افتراضات نقيّة (تدهور رشيق، لا استثناء).
    if not isinstance(raw, dict):
        return merged

    for key, value in raw.items():
        if key not in _KNOWN_TOP_KEYS:
            # مفتاح علويّ غير معروف ⇒ تجاهل آمن.
            continue

        if key in _KNOWN_SUB_KEYS:
            # قاموس متداخل (branding/units): ادمج المفاتيح الفرعيّة المعروفة فقط.
            if not isinstance(value, dict):
                # نوع مُشوَّه لقاموس متداخل ⇒ أبقِ افتراضاته كما هي.
                continue
            for sub_key, sub_value in value.items():
                if sub_key in _KNOWN_SUB_KEYS[key]:
                    merged[key][sub_key] = sub_value
        else:
            # مفتاح بسيط (language/crops): استبدل القيمة كما هي.
            merged[key] = value

    return merged
