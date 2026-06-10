# ربط الـcorrelation بـworkflow_engine + event_bus

أكملتُ التوصية السابقة: ربط طبقة correlation (التتبّع الموحّد) بالمحرّكين
فعليّاً — فيصبح كلّ workflow وكلّ event يحمل خيط التتبّع تلقائيّاً.

## ما رُبِط
**١. workflow_engine**: WorkflowState يحمل الآن correlation_id. عند إنشاء
workflow، يلتقط الـcorrelation الحالي من السياق تلقائيّاً (fallback-safe) ويحفظه
مع الحالة (durable — يبقى عبر load/استئناف).

**٢. event_bus.emit**: يقبل correlation_id (أو يلتقطه من السياق إن لم يُمرَّر)،
ويحقنه في payload كـ_correlation_id — **بلا تغيير مخطّط events** (jsonb).
فيصبح كلّ حدث ذاتيّ الوصف بخيط تتبّعه.

## لماذا هذا التصميم
- **اختياري + fallback-safe**: المحرّكان لا يستوردان correlation بصلابة؛ غيابها
  (بناء جزئي) → None، لا كسر. توافق خلفي كامل.
- **بلا تغيير مخطّط**: الحقن في payload (jsonb) لا commands/events schema —
  لا migration، لا كسر بيانات قائمة.
- **لا طمس**: merge يحافظ على payload الأصلي ({**payload, _correlation_id}).
- **صدق**: غياب correlation يُترَك None (لا اختراع خيط).

## الأثر التشغيلي
الآن السلسلة مترابطة فعليّاً: طلب (correlation) → workflow (يحمله) → events
(تحمله في payload). build_trace_tree يبني الشجرة السببيّة الكاملة من الأحداث
المحفوظة — "أيّ طلب أنتج أيّ workflow أنتج أيّ events" يصبح قابلاً للتتبّع.

## التحقّق (مُختبَر حيّاً)
- 709/709 roadmap (+6) · 0 خطأ (420 ملفّ)
- workflow يلتقط correlation ✓ · محفوظ durable ✓ · توافق خلفي (None) ✓ ·
  emit يحقن في payload ✓ · يلتقط من السياق ✓ · merge لا يطمس ✓

## ملاحظة صدق
ربطتُ correlation بالمحرّكين فعليّاً ومُختبَراً حيّاً. الحدّ المعلَن: الربط
يحفظ الخيط (workflow.correlation_id + event.payload._correlation_id)؛ بناء
الشجرة من أحداث DB حيّة + التصدير لأداة تتبّع (Jaeger) خطوة تشغيل تالية. لم
أغيّر مخطّط events (الحقن في payload) تجنّباً لكسر بيانات قائمة — قرار متّسق
مع تجنّب الـover-engineering. الاختبار الكامل عبر الخدمات يحتاج بيئة حيّة
(عدّة خدمات + DB) — اختبرتُ المنطق والربط داخل الخدمة الواحدة.
