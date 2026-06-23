# 📜 سجلّ الجلسات (append-only)

> ألحِق مدخلاً في نهاية كلّ جلسة. لا تُعدّل المدخلات السابقة. الأحدث في الأعلى.

---

## 2026-06-23 (ب) — الدماغ على main + حفظ مساحة العمل (إلهام GeoLibre)

**رأس `main`:** `033fabe` (#448، الدماغ مدموج).

- **الدماغ (#448):** دُمج `sahool-brain/` على main — الوكيل القادم يقرأ hot/index بداية الجلسة.
- **حفظ مساحة العمل (GeoLibre، الفكرة 1):** ملفّ `.sahool-project.json` قابل للتسلسل (عميل-فقط) —
  تصدير/استيراد إعدادات «مركز الخرائط» (الأساس/المؤشّر/الشفافية/المقارنة/الأدوات/التراكبات/الحقل
  المختار): [`frontend/src/lib/projectFile.ts`](../frontend/src/lib/projectFile.ts) + أزرار في
  [`frontend/src/sections/MapHub.tsx`](../frontend/src/sections/MapHub.tsx). v1 لا يحفظ مركز/تكبير
  الخريطة ولا الرسومات (مؤجّلة v2). انظر [`decisions/gis-direction.md`](decisions/gis-direction.md).

---

## 2026-06-23 — سلسلة الموبايل/الصور/QA + إنشاء الـbrain

**رأس `main` بعد الجلسة:** `0023f57` (#447).

- **auth (#437):** سياق admin على كلّ اكتساب اتّصال (`_acquire`) — العلاج الجذريّ لفشل RLS في
  التسجيل/الدخول (يكمّله ترحيل `v97_user_self_with_check.sql`).
- **الصور (#438/#439):** تفعيل صور Sentinel-2 الحقيقيّة تلقائيّاً عند إنشاء الحقل (بلا محاكاة)؛
  خادم SAM2 على GPU كـopt-in خلف `profile=gpu` (503 صادق بدونه).
- **dev-proxy (#440/#442):** توحيد وكيل تطوير Vite مع بوّابة nginx (v9) — يُصلح `npm run dev` +
  رؤية تشخيصيّة (offline/معالجة الصور).
- **QA الخرائط (#441):** سويت Playwright لبوّابة جودة MapLibre/WebGL (9 خطوات) + وظيفة CI.
- **الحقول الذرّيّة (#443):** دمج/انقسام الحقول عبر نقطتَي backend ذرّيّتين
  ([`fields.py`](../services/sahool-platform/api/routers/fields.py)) — سدّ خطر البيانات الثلاثيّة؛
  اختبار [`tests_v9/test_fields_merge_split_atomic.py`](../tests_v9/test_fields_merge_split_atomic.py).
- **تكافؤ الموبايل (#444/#445/#446/#447):** مسار سلسلة NDVI (404)، مصدر المؤشّرات الصحيح + إدارة
  المزارع، ربط أقسام مساحة العمل بالخلفيّة، السمة الداكنة الرسميّة (`AppTheme.dark`).
- **الـbrain:** إنشاء `sahool-brain/` — هذا الـvault (README/index/hot/log/dashboard +
  architecture/schema/gaps/decisions/agronomy) + قسم «الدماغ المعرفيّ» في
  [`../CLAUDE.md`](../CLAUDE.md).
