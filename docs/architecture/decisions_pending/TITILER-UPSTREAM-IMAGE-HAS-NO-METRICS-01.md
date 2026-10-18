# TITILER-UPSTREAM-IMAGE-HAS-NO-METRICS-01: TiTiler المنبعي والمقاييس

حالة القرار: معلق لدى المالك. الحالة تبقى `open`. هذه وثيقة خيارات وعقد مقترح فقط؛ لا تفويض تنفيذ.

أساس المراجعة: `1765d73a036499318beeb6d267fdaf803e4b0a40` بعد دمج #1213. مراجع الأسطر إرشادية؛ النص المصدر هو المرجع.

## العطل والأدلة

الوصف يحتاج تضييقاً: sahool-titiler اليوم داخل profile اختياري legacy-tiler، والصورة الافتراضية 0.18.6. المسار الافتراضي للمنصة وraster يمر عبر raster-tiler-service، الذي يوفر /metrics. وجود endpoint لا يثبت وحده وجود عدادات طلبات وكمون لكل مسار. لم تُشغّل الصورة المنبعية للتحقق من /metrics حياً.

- `docker-compose.v9.yml:1667`
- `docker-compose.v9.yml:869`
- `docker-compose.v9.yml:1516`
- `services/raster-tiler-service/main.py:15`

## الخيار 1: Blackbox جانبي

الملفات المتأثرة: إعدادات Prometheus وملف blackbox وcompose.

الهجرة وGATE-01: لا هجرة ولا GATE-01؛ يحتاج قرار نشر لاحقاً.

اختبارات القبول والمخاطر: توفر/كمون خارجي؛ محدود في تشخيص داخل TiTiler.

## الخيار 2: غلاف ASGI على النمط الحالي

الملفات المتأثرة: services/raster-tiler-service وإعدادات مراقبته.

الهجرة وGATE-01: لا هجرة ولا مجمدات مباشرة؛ صورة تشغيل تتغير بعد القرار.

اختبارات القبول والمخاطر: اختبارات توافق البلاطات وHTTP metrics؛ عبء صيانة إصدار الغلاف.

## الخيار 3: إيقاف دعم legacy رسمياً

الملفات المتأثرة: compose ووثائق القدرات.

الهجرة وGATE-01: لا هجرة؛ قرار منتج ونشر.

اختبارات القبول والمخاطر: إثبات عدم بقاء مستهلك يعتمد legacy؛ خطر كسر مستهلك قديم.

## التوصية وأسبابها

أوصي بتثبيت الغلاف الحالي كالمسار القانوني وتحديد قرار صريح بشأن legacy. إذا لزم تشغيل المنبعي، blackbox exporter يكفي لمراقبة التوفر الخارجي، أما RED metrics الحقيقية للطلب فتحتاج غلاف ASGI أو instrumentation داخل العملية. تُستخدم قوالب المسارات لا bbox أو field_id أو URL موقع في labels.

## قبول التنفيذ بعد قرار المالك

- مطابقة الهدف الفعلي في Prometheus للخدمة المفعلة؛ اختبار توقف الهدف وعودة التنبيه.
- للغلاف: تمرير طلبات 2xx/4xx/5xx وقياس counters/histogram مع سقف cardinality وحفظ سلوك البلاطات.
- للمصدر الجانبي: إثبات ما يقيسه probe فقط؛ لا تسمية زمن الفحص زمناً داخلياً لتوليد البلاطة.

## الحدود ومستويات القبول

وثيقة فقط، open، ولا نشر أو تبديل صورة. عزل legacy عن المسار الافتراضي لا يغلق مطلب المقاييس عند استعماله.

محلي: مراجعة مصدر ووثيقة فقط. CI: غير مقيس لهذه الوثيقة. staging: غير مقيس. الإنتاج: غير مقيس. لا هجرة ولا نشر ولا دليل جهاز بهذه الوثيقة.

## مراجع الممارسات

- [Development Seed — TiTiler core](https://developmentseed.org/titiler/packages/core/)
- [Prometheus — Instrumentation](https://prometheus.io/docs/practices/instrumentation/)
- [Prometheus — Multi-target / blackbox exporter](https://prometheus.io/docs/guides/multi-target-exporter/)
- [OpenTelemetry — HTTP route cardinality](https://opentelemetry.io/docs/specs/semconv/registry/attributes/http/)
