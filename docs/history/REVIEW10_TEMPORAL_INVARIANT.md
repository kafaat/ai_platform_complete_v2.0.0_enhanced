# المراجعة العاشرة — فرض السلطة الزمنيّة + تصحيح خطأ

## 🔴 أوّلاً: خطأ التقطته المراجعة في كودي السابق (صحّحتُه)
كودي الأوّل قارن occurred_at الوارد مع MAX(transitioned_at) — لكنّ
transitioned_at هو **وقت الإدراج (NOW())** لا وقت الحقيقة السابق. المراجعة
محقّة: المقارنة الصحيحة ضدّ آخر **occurred_at** ذي سلطة. صحّحتُ بالكامل.

## ✅ التصحيح الكامل (4 تحسينات من المراجعة)
1. **المقارنة الصحيحة**: occurred_at الوارد < آخر occurred_at مسجّل (لا
   transitioned_at/NOW). أضفتُ occurred_at لجدول الانتقالات.
2. **tiebreaker للطوابع المتساوية**: عمود seq (BIGSERIAL) — ORDER BY
   occurred_at DESC, seq DESC. يحسم occurred_at == occurred_at.
3. **LIVE/REPLAY modes**: enforcement_mode. LIVE يرفض الـregression؛ REPLAY
   يسمح (إعادة بناء تاريخيّة لا تُكسَر).
4. **لا hard-reject**: الرفض يُسجَّل في lifecycle_temporal_rejections للتسوية
   (الحقيقة المتأخّرة لا تُفقَد — تُحفَظ للمراجعة البشريّة/التصحيح الرجعي).

## الملفّات
- field_lifecycle.py: temporal guard مُصحَّح + occurred_at/enforcement_mode
- migrations/v9_lifecycle_occurred_at.sql: occurred_at + seq + جدول الرفض
- اختبار: test_temporal_invariant

## ✅ ثانياً: Correctness Closure Pipeline (Makefile)
الوثائق قدّمت Makefile/CI generic يشير لبنية **غير موجودة في SAHOOL**
(account_id/alembic/platform_sdk/verify_wiring.py). لم أنسخه حرفيّاً.
بدلاً منه: **Makefile مكيّف لبنية SAHOOL الفعليّة**:
- Stage 0 (syntax): py_compile ✓ offline
- Stage 1 (structure/logic): roadmap tests + chaos ✓ offline
- Stage 2 (infra): docker compose + health_check.sh (جهازك)
- Stage 3+4 (runtime+RLS): test_tenant_isolation.sql (جهازك، non-superuser)
- Stage 5 (adversarial): test_chaos_resilience.py
- قاعدة hard-gate: لا مرحلة تنفّذ إن فشلت السابقة
`make verify-static` يشغّل المراحل offline؛ `make verify` الحيّة على جهازك.

## التحقّق
- 376/376 · 0 خطأ ترجمة · 12 chaos · Makefile offline يعمل

## ملاحظات صدق
- **اعترفتُ بخطئي** (المقارنة الخاطئة) فور أن التقطته المراجعة وصحّحتُه — لا
  تبرير. هذا جوهر العمل: الكود يُراجَع، والأخطاء تُصحَّح علناً.
- الـMakefile الأصلي في الوثائق لبنية أخرى (account_id لا tenant_id، alembic
  لا raw SQL). تكييفه لـSAHOOL أصدق من نسخه (لكان أشار لملفّات وهميّة).
- temporal guard مُتحقَّق منه بنيويّاً + اختبار. **لم يُشغَّل ضدّ DB حيّ**
  (لا postgres) — اختبر السيناريو (حدث متأخّر) بعد النشر.
- الرفض-للتسوية يحلّ تحذير المراجعة من "الصرامة المفرطة" (تصحيح offline
  شرعي لا يُرفَض للأبد — يُحفَظ).
