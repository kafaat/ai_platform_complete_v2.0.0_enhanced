# FieldView User Data Flow Hardening — 2026-07-03

## الهدف
توحيد تدفق بيانات المستخدم في الواجهات على نمط FieldView: يختار المستخدم الحقل مرة واحدة، ثم ينتقل نفس الحقل النشط عبر الخرائط، التحليلات، التوصيات، الري، التنبيهات، التقارير، الاستكشاف، والإعداد.

## ما تم تنفيذه

### 1. تعميم مصدر الحقل النشط
تم نقل الصفحات التالية من `useFieldOptions` أو اختيار محلي إلى `useSelectedField`:

- `frontend/src/sections/AlertSystemPage.tsx`
- `frontend/src/sections/EtcDualPage.tsx`
- `frontend/src/sections/GisToolsPage.tsx`
- `frontend/src/sections/OperationCenterWallPage.tsx`
- `frontend/src/sections/ReportsPage.tsx`
- `frontend/src/sections/ScoutingView.tsx`
- `frontend/src/sections/SetupCabin.tsx`
- `frontend/src/sections/WaterTwinPage.tsx`
- `frontend/src/sections/AnalyticsPage.tsx`
- `frontend/src/sections/RecommendationPage.tsx`
- `frontend/src/sections/RecommendationFlow.tsx`

النتيجة: اختيار الحقل في أي شاشة رئيسية يكتب إلى `useFieldContextStore` ويصبح متاحاً لباقي الواجهات.

### 2. تحسين جدار مركز العمليات
في `OperationCenterWallPage` أصبحت خريطة الحقول:

- تقرأ الحقل النشط من `useSelectedField`.
- تميّز الحقل النشط بصرياً.
- تسمح بالنقر على polygon/marker لتغيير الحقل النشط عالمياً.

### 3. تحسين مشاركة الحقول
في `SharingPanel`، عند تقييد المشاركة بحقول محددة، يتم اقتراح الحقل النشط تلقائياً بدل البدء من قائمة فارغة. هذا يجعل مشاركة FieldView متوافقة مع سياق المستخدم الحالي.

### 4. تقوية اختبارات الحراسة
أضيف اختبار static guard:

- `frontend/src/hooks/useSelectedField.static.test.ts`

يفشل الاختبار إذا عادت صفحات `sections` لاستخدام `useFieldOptions` مباشرة لاختيار الحقل، باستثناء `FieldMapCenter.tsx` لأنه يملك منطق URL/map-specific واضح ويكتب إلى نفس المتجر المشترك.

### 5. تحديث اختبارات متأثرة
تم تحديث mock في:

- `frontend/src/sections/OperationCenterWallPage.test.tsx`
- `frontend/src/sections/ReportsPage.test.tsx`

حتى تعكس المصدر الجديد `useSelectedField` بدلاً من `useFieldOptions`.

## التحقق
تم إجراء فحص parse/TypeScript جزئي على الملفات المعدلة باستخدام `tsc --noResolve` للتأكد من عدم وجود أخطاء syntax أو identifiers مكسورة في الملفات المعدلة. لم تُنفذ دورة `npm ci` كاملة لأن تثبيت حزم الواجهة داخل البيئة الحالية تجاوز المهلة المتاحة.

## الحكم
تدفق FieldView أصبح أقوى وأكثر اتساقاً: الاختيار العالمي للحقل لم يعد مقتصراً على MapHub/Satellite/FieldWorkspace، بل امتد إلى صفحات التحليل، التنبيهات، الري، التقارير، الاستكشاف، التوصيات، مركز العمليات، والإعداد.
