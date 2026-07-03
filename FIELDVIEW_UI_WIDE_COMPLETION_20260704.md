# FIELDVIEW UI-WIDE COMPLETION — 2026-07-04

## الهدف
إغلاق الفجوة المتبقية في الواجهة بحيث لا يبقى اختيار الحقل في الشاشات الأساسية كحالة محلية منعزلة، بل يمر عبر مصدر الحقيقة FieldView:

- `useSelectedField`
- `useFieldContextStore` فقط داخل hook/نقاط دخول موثقة
- `resolveActiveField` لقواعد route/stored/auto/none

## الشاشات/المكونات التي تم تحويلها أو تقويتها

### شاشات تشغيلية وتحليلية
- `AlertSystemPage.tsx`
- `EtcDualPage.tsx`
- `GisToolsPage.tsx`
- `OperationCenterWallPage.tsx`
- `RecommendationFlow.tsx`
- `RecommendationPage.tsx`
- `ReportsPage.tsx` — `FieldSummaryView` أصبح FieldView-aware، مع بقاء `useFieldOptions` فقط لتجميع تقارير كل الحقول.
- `ScoutingView.tsx`
- `WaterTwinPage.tsx`
- `ChatbotPage.tsx`

### شاشات/نماذج ذات field_id اختياري
- `DevicesPage.tsx` — اقتراح الحقل النشط تلقائياً عند تسجيل جهاز.
- `DocumentsPage.tsx` — اقتراح الحقل النشط تلقائياً عند إنشاء وثيقة.
- `FieldIntelligencePage.tsx` — اقتراح الحقل النشط تلقائياً عند طلب التحليل.
- `PestEscalationPage.tsx` — اقتراح الحقل النشط تلقائياً عند تشغيل تدفق تصعيد الآفة.

### مكونات مساعدة
- `SharingPanel.tsx` — اقتراح الحقل النشط داخل مشاركة الحقول.
- `SQLEditor.tsx` — استخدام `useSelectedField` وتحديث الحقل النشط عند إدراج field id.

## التحسينات السلوكية

1. القوائم التي تختار حقلاً أصبحت تقرأ من `activeFieldId` وتكتب إلى `setFieldId` العالمي.
2. صفحات التوصيات/التقارير/ETc/Water Twin/GIS/Scouting لم تعد تبدأ باختيار محلي منفصل يختلف عن MapHub.
3. نماذج التسجيل/الوثائق/الذكاء/الآفات تقترح الحقل النشط دون منع المستخدم من تغيير القيمة عند الحاجة.
4. Chatbot يمرر الآن:
   - `field_id`
   - `active_field_name`
   - `ai_context_pack`
   ضمن طلب AI runtime.
5. إضافة static guard جديد يمنع تراجع المسار الأساسي عن FieldView.

## الاختبار الجديد

أضيف:

```text
frontend/src/hooks/fieldViewUiWide.static.test.ts
```

يغطي:

- الشاشات الأساسية يجب أن تحتوي `useSelectedField`.
- `ChatbotPage` لا يقرأ `useFieldContextStore` مباشرة.
- `SharingPanel` و `SQLEditor` يجب أن يكونا FieldView-aware.

## نتائج التحقق

```text
npm ci --legacy-peer-deps --ignore-scripts
نجح — 0 vulnerabilities

npm run typecheck
نجح

npm run build:docker
نجح

FieldView targeted tests
5 files passed / 16 tests passed

field-segmentation tests
29 passed
```

## ملاحظات صادقة

- `FieldMapCenter.tsx` بقي نقطة دخول موثقة لأنها تدير الربط العميق/المركز وقراءة الرابط.
- `ReportsPage.tsx` و `SetupCabin.tsx` يمكن أن يستخدما `useFieldOptions` كقائمة/تجميع لكل الحقول، وليس كمصدر اختيار منفصل للحقل النشط.
- بعض صفحات مثل `IrrigationOpsPage` تحتوي حقول `field_id` داخل نماذج شبكات/صمامات، وهي مدخلات ربط اختيارية وليست شاشة تحليل FieldView رئيسية؛ لم يتم قفلها على الحقل النشط حتى لا نكسر سيناريوهات تسجيل أكثر من عنصر على حقول مختلفة.
