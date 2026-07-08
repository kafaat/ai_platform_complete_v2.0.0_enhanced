-- migrations/v152_deprecate_recommendation_feedback.sql
--
-- v152: إيقاف جدول recommendation_feedback الميّت (جسر #4 من تدقيق إغلاق الحلقة).
--
-- التدقيق (2026-07-08): recommendation_feedback (v_ai_recommendation_runtime) بلا **أيّ كاتب
-- أو قارئ** في الكود. الفحص الأعمق أثبت أنّه **مكرّر ميّت** — كلّ أعمدته لها موطن حيّ مرجعيّ:
--   • القبول + الغلّة (accepted/predicted/actual_yield) ⇒ recommendation_outcomes (v49)
--     يكتبها recommendations.py/fields.py ويقرؤها learning.py (حيّة، مرجعيّة).
--   • التكلفة (actual/standard_cost) ⇒ دفتر العمليّات الاقتصاديّ (farm_operations_ledger).
--   • الماء (actual/standard_water) ⇒ دفتر المياه (water_ledger).
--
-- لذلك **لا يُوصَل كاتب** (سيُعيد تجزئة «النموذجَين» التي حلّها جسر #3). الحلّ الصادق: **إيقاف
-- مُوثَّق** — تعليق يُوجّه للمسارات المرجعيّة، دون DROP (سلامة البيانات/توافق خلفيّ). يحوّل «الجدول
-- الميّت الصامت» إلى قرار مُوثَّق يمنع إحياءه. idempotent (COMMENT يُعاد ضبطه). بعد v151.

BEGIN;

COMMENT ON TABLE recommendation_feedback IS
    'DEPRECATED (v152، جسر #4): جدول مكرّر ميّت بلا كاتب/قارئ. المسارات المرجعيّة الحيّة: '
    'القبول+الغلّة ⇒ recommendation_outcomes (v49)؛ التكلفة ⇒ farm_operations_ledger؛ '
    'الماء ⇒ water_ledger. لا تُوصِّل كاتباً هنا (يُعيد تجزئة النتائج). لا يُحذَف (سلامة بيانات).';

COMMIT;
