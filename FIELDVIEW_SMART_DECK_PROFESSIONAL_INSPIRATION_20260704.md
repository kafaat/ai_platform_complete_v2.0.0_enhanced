# FIELDVIEW SMART DECK PROFESSIONAL INSPIRATION — 2026-07-04

## الهدف
تحويل نمط FieldView من مجرد “اختيار حقل مشترك” إلى تجربة تشغيلية أقرب لأفضل تطبيقات الزراعة الرقمية: الحقل النشط يقود **أفضل إجراء تالٍ** بناءً على الصور، التنبيهات، المهام، وسجل الحقل.

## الإلهام المراجع
- FieldView: Field Health Imagery، scouting، real-time alerts، pins، prescriptions، وتحليل الخرائط والنتائج.
- John Deere Operations Center: Field/Work Analyzer، مواقع المعدات، تنبيهات، بيانات تنفيذ وتشغيل.
- OneSoil: NDVI/moisture layers، satellite history، field-level weather، scouting notes، spraying window recommendations.
- Farmable: field maps، job planner، spray records، pest monitoring، harvest tracker، وربط السجلات بالخريطة.

## التنفيذ
### 1) FieldView context store professionalized
`frontend/src/hooks/useFieldContext.ts`
- selectedFieldName
- selectedAt
- selectionSource: user/route/auto/restore/system
- selectionReason
- clearSelectedField

### 2) Active field resolver
`frontend/src/lib/fields.ts`
- resolveActiveField(options, routeFieldId, storedFieldId)
- Route field صالح يفوز.
- Stored field صالح يستخدم كاستعادة.
- Stale route/stored يسقطان تلقائياً لأول حقل متاح.
- لا حقول = empty state صادق.

### 3) useSelectedField upgraded
`frontend/src/hooks/useSelectedField.ts`
- routeFieldId input
- routeFieldIsInvalid
- storedFieldIsInvalid
- selectionReason
- metadata sync to store

### 4) FieldView Smart Deck
`frontend/src/lib/fieldViewActionDeck.ts`
`frontend/src/components/fieldview/FieldViewInsightStrip.tsx`

يعرض 5 بطاقات كحد أقصى:
- imagery: جاهزية/قدم صور Sentinel والتوصية بتجهيز سنتين.
- scouting: تنبيهات أو اقتراح زيارة ميدانية.
- operations: مهام مفتوحة أو إنشاء مهمة.
- records: اكتمال سجل الحقل crop/area.
- context: reconciliation عند stale route/stored field.

### 5) Integration في MapHub
`frontend/src/sections/MapHub.tsx`
- تمرير routeFieldId إلى useSelectedField.
- إضافة FieldViewInsightStrip أعلى خريطة الحقول.
- ربط CTA مباشرة بـ:
  - تشغيل تجهيز سنتين.
  - فتح timeline.
  - إظهار التنبيهات.
  - إظهار المهام.

### 6) MyFieldsPage metadata
`frontend/src/sections/MyFieldsPage.tsx`
- عند فتح حقل يتم تخزين id + name + source:user + reason:my-fields-open.

## الاختبارات والتحقق
- npm ci --legacy-peer-deps --ignore-scripts: نجح، 0 vulnerabilities.
- npm run typecheck: نجح.
- FieldView tests: 3 files passed / 10 tests passed.
- npm run build:docker: نجح.
- field-segmentation: 29 passed.

## الملفات الجديدة
- frontend/src/lib/fieldViewActionDeck.ts
- frontend/src/lib/fieldViewActionDeck.test.ts
- frontend/src/lib/fieldViewResolver.test.ts
- frontend/src/components/fieldview/FieldViewInsightStrip.tsx
- frontend/src/hooks/useSelectedField.professional.static.test.ts

## الحكم
تم رفع FieldView من “اختيار حقل مشترك” إلى “سياق تشغيلي ذكي” يقترح الإجراء التالي على طريقة التطبيقات الزراعية الاحترافية، مع استمرار الصدق: لا بيانات ملفقة، ولا توصيات تنفيذية بلا دليل.
