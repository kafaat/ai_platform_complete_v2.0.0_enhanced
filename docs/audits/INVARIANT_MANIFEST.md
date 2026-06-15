# Invariant Manifest — تنفيذ مكيّف (مراجعة 11/12)

## ما طلبته الوثائق
DSL واحد للـinvariants + محرّك تنفيذ + Makefile bootstrap + drift detector +
"self-verifying/self-healing runtime".

## ما نفّذتُه (الصحيح القابل للتطبيق) ✅
- **invariants.yaml**: manifest فعلي يربط كلّ invariant في SAHOOL بمتحقّقه
  الفعلي (5 طبقات L0-L3 + FREEZE). مصدر واحد للحقيقة.
- **scripts_v9/verify_invariants.py**: مشغّل رفيع يقرأ الـmanifest ويشغّل
  المتحقّقات **الفعليّة** (py_compile, roadmap 376, chaos 12). يُبلّغ بصدق أنّ
  L3 (RLS الحيّ) يحتاج جهازك بدل ادّعاء فحصه.
- **Makefile: verify-invariants** target.

## ما رفضتُ نسخه (over-engineering / بنية وهميّة) ❌
الوثائق DSL يشير لبنية **غير موجودة في SAHOOL**:
- `account_id` (SAHOOL يستخدم tenant_id/app.current_tenant)
- `verify_wiring.py`, `extract_from_envelope`, `apply_account_guc` (لا وجود لها)
- `platform_sdk`, `reference-services` (لا SDK في SAHOOL)
نسخها = manifest يشير لملفّات وهميّة (false green). كيّفتُه لبنية SAHOOL الحقيقيّة.

- **drift detector** (AST↔runtime): يحتاج verify_wiring.py (AST verifier) غير
  موجود في SAHOOL. لا أبني AST verifier وهميّاً لأقارنه. الفحص البنيوي مدموج
  في الاختبارات أصلاً.
- **"self-healing runtime"**: مفهوم تأمّلي بعيد عن مرحلة المشروع — لم أبنِه.

## ملاحظة صدق حاسمة (over-engineering)
المراجعات (11/12) بدأت تدفع نحو هندسة تحقّق مجرّدة متزايدة: DSL → محرّك →
self-verifying → self-healing. هذا **منزلق over-engineering**: بناء أطر تحقّق
ضخمة تتجاوز حاجة المشروع الفعليّة. SAHOOL لديه أصلاً 376 اختباراً + chaos +
SQL isolation تغطّي الـinvariants الحقيقيّة. القيمة المضافة من manifest =
**تنظيم** (مصدر واحد) لا قدرة جديدة. بنيتُ النسخة المنظّمة الرفيعة؛ تجنّبتُ
الإطار الضخم الذي يضيف تعقيداً معرفيّاً بلا عائد متناسب.

## الاستخدام
- `make verify-invariants` — يشغّل الـmanifest (static، offline)
- `make verify-static` — الطبقات offline كاملة
- `make verify` — الحلقة الكاملة (جهازك، postgres حيّ)

## التحقّق
- 376/376 · 0 خطأ ترجمة · runner يعمل (L0-L2 ✓، L3 يُبلّغ بصدق)
