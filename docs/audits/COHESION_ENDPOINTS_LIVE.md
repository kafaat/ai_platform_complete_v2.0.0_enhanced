# إكمال تغذية Runtime Cohesion: النقطتان الحيّتان

بعد ربط farm_memory + simulation بحلقة القرار (في الكود)، بُنيت النقطتان
اللتان تغذّيان المحوّلين الحيّين — لتكتمل السلسلة من الطلب إلى القرار.

## النقطة ١: GET /api/v1/fields/{field_id}/history
**الغرض**: يغذّي memory_adapter بالسياق التاريخي للحقل.
- يجلب أحداث الحقل من events table عبر tenant_connection (**RLS مُطبَّق** —
  كلّ مستأجر أحداثه فقط، لا IDOR).
- يستنتج issue_tags من نوع الحدث/الحمولة (ملوحة/إجهاد مائي/آفة/تدهور/حراري)
  عبر _issue_tags_from_event — مدخل كشف التكرار (≥مرّتين = قضيّة متكرّرة).
- **صدق**: عند تعطّل DB (_DB_POOL=None) → events فارغة + note صريح (لا تاريخ
  مخترَع). عند خطأ استعلام → error مُعلَن.

## النقطة ٢: POST /api/v1/simulate/what-if
**الغرض**: يغذّي simulate_adapter بأثر السيناريو المتوقّع.
- يشغّل simulate_wofost **مرّتين**: baseline (مرويّ) مقابل scenario (بلا ريّ)،
  ويقارن المحصول (yield_t_ha) والماء (irrigation_needed_mm).
- محاكاة علميّة حقيقيّة (WOFOST + طقس Open-Meteo حيّ) — لا أرقام مخترَعة.
- recommended_action_helps: هل الريّ الموصى به يحفظ >2% محصول؟
- **صدق**: lat/lon إلزاميّان (لا محاكاة بلا موقع)؛ تعذّر النموذج/الطقس →
  available=False + سبب (لا أرقام مخترَعة).

## السلسلة المكتملة الآن (end-to-end)
```
POST /field-intelligence/analyze
  → build_live_adapters() [memory_fn + simulate_fn]
  → run_field_intelligence (graph القرار)
    → memory_fn → GET /fields/{id}/history → events (RLS) → recurring_issues
                → يدخل decision.historical_context_ar
    → simulate_fn → POST /simulate/what-if → WOFOST×2 → أثر متوقّع
                → يدخل decision.simulation_caveat_ar
  → النتيجة: state + decision + memory + simulation + alerts (graph واحد)
```

## التحقّق (مُختبَر)
- 686/686 roadmap (+6) · 0 خطأ (418 ملفّ)
- استنتاج القضايا + كشف التكرار (≥2) مُختبَر منطقيّاً ✓
- النقطتان موصولتان بالمحوّلين (نفس المسارين) ✓
- صدق التعذّر (DB معطّل / نموذج متعذّر) ✓

## ملاحظة صدق
أكملتُ تغذية Runtime Cohesion: النقطتان الحيّتان مبنيّتان وموصولتان بالمحوّلين،
والسلسلة كاملة من الطلب إلى القرار. الحدود المعلَنة (تُختبَر على جهازك):
1. **/history** يحتاج PostgreSQL مفعّلاً + أحداث في events table؛ بدونه يُرجِع
   فارغاً بصدق. تدفّق RLS الفعلي يُختبَر بقاعدة حيّة.
2. **/simulate/what-if** يحتاج اتّصال شبكة لـOpen-Meteo (داخل simulate_wofost)؛
   بيئتي معزولة فلم أشغّله حيّاً — اختبرتُ المنطق (مقارنة، صدق التعذّر) لا
   النداء الفعلي للطقس. شغّله على جهازك لحقل Sunaidar وتأكّد من أرقام المحصول.
3. **issue_tags** استنتاج أوّلي من أنواع الأحداث الحاليّة — قد تحتاج توسيعاً
   حين تتبلور أنواع أحداث جديدة. عايِر عتبة التكرار (≥2) بتاريخ حقيقي.
لم أزعم تشغيلاً حيّاً للطقس أو DB — المنطق مبنيّ ومُختبَر، والتغذية الحيّة على
بيئة التشغيل.
