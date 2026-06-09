# الأتمتة — التحقّق والإصلاح

## ملاحظة صدق أوّليّة: الأتمتة لم تكن ناقصة
فحصتُ فوجدتُ الأتمتة **مكتملة وموصولة** أصلاً:
- scheduler.py مُشغّل في lifespan (start/stop) + 3 مهامّ (طقس/صور/نضارة)
- weather_automation + imagery_automation: دوال حقيقيّة + استمرار DB + fallback
- 0 TODO، الكلّ موصول end-to-end

لم أبنِ أتمتة جديدة (لم تكن ناقصة). بدلاً منه: **أصلحتُ خطأً حقيقيّاً**.

## الخطأ الحقيقي المُصلَح
imagery_automation._trigger_indicators() كان يرسل لـraster /process:
  {"raster_url":..., "indicator":...}
لكنّ ProcessRequest **يتطلّب** tenant_id + source_format + bands → الطلب كان
**سيفشل التحقّق صامتاً** (الأتمتة تكتشف الصورة لكن حساب المؤشّر يفشل).
وأيضاً: بلا scene_id/capture_datetime → النتيجة موسومة غير قابلة للإعادة (#7).

## الإصلاح (لا يكسر شيئاً)
1. TrackedField + tenant_id (يُحمَّل من DB، يُحفَظ، يُمرَّر)
2. _trigger_indicators يرسل payload كاملاً: tenant_id + source_format=cog +
   bands + scene_id + capture_datetime (provenance)
3. endpoint register-field: أضيف get_current_user → tenant من التوكن (أمان)
4. _persist_field + load_from_db: يخزّنان/يحمّلان tenant_id

## إصلاح ثانوي (regression أحدثتُه ثمّ صحّحتُه فوراً)
تغيير ترتيب أعمدة INSERT كسر mock في test_automation_persistence (يقرأ
بالموضع). حدّثتُ الـmock ليطابق الترتيب الجديد (+tenant_id). **اعتراف**:
أحدثتُ الكسر بالتغيير، التقطه التحقّق، صحّحتُه قبل التسليم.

## التحقّق
- 377/377 (= 376 + اختبار الأتمتة الجديد) · 0 خطأ ترجمة · evidence overall=pass
- اختبار وظيفي: payload يحمل كلّ الحقول المطلوبة + provenance + tenant صحيح

## ملاحظة صدق
- لم يُشغَّل ضدّ raster حيّ (لا خدمة في البيئة) — اختبار الـpayload بـstub.
  اختبر التدفّق الكامل (صورة جديدة → /process → نتيجة) بعد النشر.
- لا fallback مكسور: بلا حقول → لا يضرب raster (صدق محفوظ).
