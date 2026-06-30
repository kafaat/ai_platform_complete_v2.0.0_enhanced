# DRAWING_TOOLS_REVIEW_REPORT — 2026-06-30

تحقّق مستقلّ من مراجعة أدوات الرسم (مقابل الكود الفعليّ على `main`)، مع إصلاح الفجوة
على الفرع القانونيّ. الخلاصة: **المراجعة صحيحة في جوهرها، لا مبالغة** — مع تدقيقَيْن.

## ما تأكّد صحيحاً (بالكود)
- **leaflet-draw خام بدل react-leaflet-draw** (توافق React 19): `frontend/src/components/maphub/DrawControl.tsx` — لا يستورد `react-leaflet-draw`، يستخدم `L.Control.Draw` مباشرةً، ويُضيف الشكل إلى `FeatureGroup` **قبل** `onCreated`.
- **قياس MapHub**: مضلّع (مساحة) + خطّ (طول) عبر `MeasureTools` + Turf (`HubMap.tsx`).
- **إنشاء الحقل المتقدّم** (`AddFieldWithMap.tsx`): مضلّع · دائرة محوريّة تفاعليّة · مستطيل مُدار · Snap للحدود · Undo/Redo · **مقبض مركز قابل للسحب** لتحريك الشكل.
- **أدوات التقسيم/الدمج ومناطق الوصفات** تستخدم رسماً محدوداً حسب الوظيفة.

## الفجوة — حقيقيّة (لا مبالغة) ✅
الرسم/القياس (`MeasureTools`) ودبابيس الاستكشاف (`PinClickHandler`) **كلاهما يستهلك نقرات الخريطة**:
- `HubMap.tsx`: `<PinClickHandler enabled={pinMode} />` **و** `{drawTools && <MeasureTools />}` يُصيَّران معاً بلا حارس.
- `HubMap.tsx`: `click(e) { if (enabled) onAddPin(...) }` تعمل أثناء الرسم.
- لو فُعِّل `drawTools` و`pinMode` معاً ⇒ كلّ نقرة قياس تُسقط دبّوساً بالخطأ.

**تدقيق:** التبادل `compare ↔ pinMode` كان موجوداً سلفاً (`MapHub.tsx`)؛ الناقص فعليّاً
كان `drawTools ↔ pinMode`. فالفجوة دقيقة لكنّها حقيقيّة.

## الإصلاح المطبَّق (على `main`)
`frontend/src/sections/MapHub.tsx` — حصر متبادل كامل بين الثلاثة (رسم/قياس · دبابيس · مقارنة):
تفعيل أيٍّ يُعطّل الآخرَيْن. حارس ساكن جديد `DrawingTools.static.test.ts` يثبّت:
عدم استيراد react-leaflet-draw · ترتيب addLayer→callback · بقاء كلا المعالِجَيْن · الحصر المتبادل.

## ملاحظة على «v30»
الملفّان اللذان ذكرتهما المراجعة (`DrawingTools.static.test.ts` + هذا التقرير) لم يكونا
على `main` قبل هذا الالتزام — كانا في حزمة v30 خارجيّة. هذا الالتزام يجلب الإصلاح والحارس
إلى الفرع القانونيّ `main` ليبقى متّسقاً.

## التحقّق
`npm run typecheck` (0) · `DrawingTools.static.test.ts` 5/5 · `InteractiveDrawLayer.test.ts` أخضر · بقيّة حُرّاس maphub خضراء.
