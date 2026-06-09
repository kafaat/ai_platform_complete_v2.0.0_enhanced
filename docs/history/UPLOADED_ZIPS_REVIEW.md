# مراجعة الـZIPات الثلاثة المرفوعة — ماذا أخذنا، ماذا رفضنا، ولماذا

تاريخ المراجعة: ضمن جلسة تنفيذ خارطة الطريق (بعد إكمال البنود ٧/٨/٩).

الـZIPات: `sahool_fieldops_modules_v16.zip`، `sahool_tier0_complete.zip`،
`sahool_unified_v16_fixed.zip` (إجمالي ٤٧ ملفّ Python + ٣ Dart + ٥ SQL).

## المنهج
طبّقنا قاعدتَينا: **فحص الادّعاء بالكود** (ast.parse + قراءة فعليّة) و**لا
ثوابت مُختلقة**. صنّفنا كلّ مكوّن: نأخذه / نرفضه / نؤجّله — بمبرّر.

---

## ✅ ما أخذناه (مفيد + صحيح + يلائم بنية سهول)

### `trial_randomization.py` (مُستخرَج ومُكيَّف)
المصدر: `sahool_unified_v16_fixed/backend/trials/randomization.py`.
**الفكرة القيّمة:** توزيع عشوائي **حتمي قابل للتحقّق** عبر hash بدل
`np.random.seed(timestamp)` الساذج (الذي في مرفقات سابقة). يتيح:
- إعادة إنتاج التوزيع نفسه بالضبط (reproducibility)
- كشف التلاعب عبر `seed_hash`
- حماية البذرة الخام (يكشف الـhash فقط)

**ما فعلناه:** استخرجنا المنطق النقي فقط، وأزلنا طبقة
SQLAlchemy/async/event_store التي لا تلائم بنية سهول (`api/` pure-logic).
اختُبر: حتميّة ✓، كشف تلاعب ✓، رفض <4 كتل ✓. تمهيد مباشر للبند ١١.

---

## ❌ ما رفضناه (مع المبرّر)

### ١. كلّ ملفّات Dart (٣ ملفّات)
`fieldops_services.dart`، `tier0_services.dart`، `tier0_models.dart`.
**السبب:** تطبيق سهول **React Native + TypeScript**، صفر Dart. هذا الخطأ
(افتراض Flutter) تكرّر في عدّة مرفقات وصحّحناه كلّ مرّة. أعدنا بناء جزء
الموبايل (WalkPlanScreen.tsx، pinRepo.ts) بـRN.

### ٢. البنية المعماريّة (`backend/trials/`, `backend/timeline/`...)
**السبب:** المرفقات تستخدم SQLAlchemy + pydantic + AsyncSession + بنية
حِزَم منفصلة. بنية سهول الفعليّة: `api/*.py` pure-logic بلا ORM (٢٠ من ٤٧
ملفّاً مرفوعاً مرتبط بـSQLAlchemy، ١٧ بـasync DB — لا يعمل في بيئتنا بلا
PostgreSQL). نسخها = تفرّع معماري مكلف بلا فائدة.

### ٣. ملفّان لا يُحلَّلان (syntax errors)
`tier0_complete/backend/tests/test_media_lifecycle.py` و
`fieldops_modules_v16/backend/pins/models.py` — فشلا في ast.parse. كود
معطوب لا يدخل المشروع.

### ٤. الـSQL views فيها خطأ DATE_TRUNC
`V001__fieldops_modules.sql` (في zipين) يستخدم
`DATE_TRUNC('year', timestamp_utc)` داخل تعبير view — نفس صنف الخطأ الذي
أصلحناه سابقاً (date_trunc غير IMMUTABLE في فهارس/تعابير معيّنة). لن نُدخِله
دون اختبار ضدّ PostgreSQL حقيقي (غير متاح).

### ٥. تكرار ما بنيناه أصلاً (timeline/pins)
المرفقات تعيد تنفيذ Field Timeline و Scouting Pins — بنيناهما فعلاً
(`field_timeline.py`، `scouting_pins.py`، `pinRepo.ts`) بنسخة pure مُختبَرة
(٢٩/٢٩). لا داعي للاستبدال.

---

## ⏸ ما أجّلناه (مفيد لكن لا حاجة آنيّة)

### `differential.py` — JSON Patch (RFC 6902) للمزامنة التفاضليّة
نقي (٣٥٤ سطراً، بلا DB) وجيّد. **لكن:** المزامنة في سهول على جانب الموبايل
(TypeScript: `syncEngine.ts` + `offline_queue.ts`) وتكفي حالياً. نقل تطبيق
Python للـbackend = حلّ لمشكلة لا نواجهها بعد. نعيد النظر لو احتجنا دلتا
مزامنة على مستوى الخادم.

### مفاهيم `event_store` / `capabilities` / `tenant_isolation`
أفكار سليمة (سجلّ أحداث ثابت، عزل مستأجرين، صلاحيّات) — لكنّ سهول عندها
نظائر (`event_replay`, `data_lineage`, RLS، RBAC). لا نُدخِل تطبيقاً موازياً.

---

## الخلاصة
من ٤٧ ملفّ Python مرفوع، **مكوّن واحد** كان يستحقّ الاستخراج
(`trial_randomization`) لأنّه يقدّم تحسيناً حقيقيّاً (حتميّة قابلة للتحقّق)
يلائم مبدأ "الصدق الإحصائي". الباقي إمّا مكرّر، أو بنية خاطئة (Dart/ORM)، أو
معطوب، أو مؤجّل. هذا اتّساق مع قاعدتنا: لا نُدخِل كوداً لمجرّد وجوده.
