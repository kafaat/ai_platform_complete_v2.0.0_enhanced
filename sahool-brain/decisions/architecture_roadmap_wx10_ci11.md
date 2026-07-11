# خارطة الطريق المعماريّة بعد Zero-Legacy — WX-10 … CI-11 → Agricultural OS

**المصدر:** قرار المستخدم (رسالة 2026-07-11، أثناء إغلاق راتشِت ET0 #4). **الحالة:** مُعتمَدة كتوجيه
استراتيجيّ لِما بعد إفراغ allowlist ET0/GDD (`assert len==0`). **المبدأ الناظم:** الحقيقة الواحدة
لكلّ نطاق (State Product) + الملكيّة الواحدة للحساب + العقود قبل المستهلكين — تقليل التعقيد الحاليّ لا زيادته.

## الشرط المسبق (قيد الإنجاز)
إتمام **ملكيّة محرّك الطقس الكاملة**: راتشِتات ET0 #5 (`fao56`) + #6 (`core/engines/et0.py`) ⇒
allowlist=0 + حارس `assert len(temporary_legacy_allowlist) == 0`. القدرة على بناء CanonicalWeatherState
تعتمد على أنّ الطقس يُحسب في مكان واحد.

## التسلسل المُعتمَد

### WX-10 — CanonicalWeatherState (الحقيقة الوحيدة للطقس)
- **State Product** (مثل CanonicalCropState) لا مجرّد DTO: يحمل `version · owner · quality · availability ·
  confidence · provenance · evidence · limitations`.
- يحوي: current · forecast · historical · astronomy · ET0 · VPD · GDD · DTR · heat_load · chill_hours ·
  frost_risk · operation_windows.
- **الانعكاس المعماريّ:** ET0/VPD/GDD/… تصبح **مشتقّات (Derived Products/Views) منه** لا العكس. لا View
  يقرأ Weather Engine مباشرةً — الكلّ يقرأ CanonicalWeatherState.
- **بذرة مُنجَزة:** راتشِت #4 أضاف `availability` map + `analysis_status` إلى weather-analytics — أوّل تطبيق
  للمفهوم؛ التعميم على كلّ منتجات المحرّك هو WX-10.

### WX-11 — Agricultural Capability Registry
سجلّ **قدرات تشغيليّة** لا مؤشّرات فقط. كلّ قدرة: `owner · consumers · contract · status · availability ·
provenance`. أمثلة: et0/gdd/vpd/crop_water/root_depth/stress/yield/nitrogen/disease. **يصبح مرجع CI.**

### CI-7 — Canonical Inputs
Crop لا يعرف المنتجات الجزئيّة إطلاقاً؛ يقرأ فقط: CanonicalWeatherState · CanonicalWaterState ·
CanonicalSpectralState · CanonicalSoilState.

### CI-8 — CropRecommendationContext (المنتج الوحيد الذي يقرؤه Decision)
يحوي: crop_state · weather_state · water_state · stress_state · confidence · limitations · provenance —
ولا شيء آخر. (جزء منه قائم عبر Crop Intelligence/field_state.)

### CI-9 — Policy Engine
فصل قواعد الأعمال الموزّعة إلى: Crop · Water · Weather · Regional · Cultivar · Business Policies —
فيصير Crop Engine عامّاً (generic).

### CI-10 — Agricultural Knowledge Layer (Knowledge Products، لا RAG)
Crop/Disease/Nutrient/Irrigation/Phenology/Operations/Regional Knowledge — كلٌّ بـ version/provenance/
confidence/source. المسار: Knowledge → Crop Intelligence → Decision.

### CI-11 — Crop Learning Engine (نقطة التحوّل الكبرى؛ ليس تدريب LLM)
الحلقة: Recommendation → Decision → Execution → Outcome → Learning → Policy Update. تُولّد: Policy
Confidence · Regional Calibration · Cultivar Calibration · Threshold Drift · Recommendation Accuracy.

### النهاية — Agricultural Operating System
Weather → Water → Raster → Soil → Crop Intelligence → Knowledge → Decision → Execution → Learning،
جميعها مترابطة عبر عقود State Products.

## القاعدة الحاكمة (التعديل الأساسيّ)
ابنِ **كلّ Canonical\*State كـState Product** (version/owner/quality/availability/confidence/provenance/
evidence/limitations)، ثمّ اجعل المنتجات الجزئيّة مشتقّات منه — لا DTO خام.
