-- ═══════════════════════════════════════════════════════════════════
-- v241_edge_idempotency_tenant_scoped.sql — CP997-05 (GATE-01 batch 2, 2026-11-07)
-- ═══════════════════════════════════════════════════════════════════
-- `uq_edge_idempotency` (v9) كان فريداً **عالميّاً** على idempotency_key بينما بحثُ الصفّ
-- القائم في routers/edge.py مقيّدٌ بالمستأجِر. فمفتاحٌ يملكه مستأجِرٌ آخر يصطدم عند الإدراج،
-- ثمّ لا يُعثَر عليه تحت RLS، فيُرفَع 409 على حدثٍ صالح. الفهرسُ يصير مقيَّداً بالمستأجِر،
-- وهدفُ ON CONFLICT في الراوتر يتبعه في الرقعة نفسها.
--
-- الترتيب داخل المعاملة نفسها: يُنشأ الجديد أوّلاً ثمّ يُحذَف القديم، فلا تمرّ لحظةٌ بلا
-- فهرسٍ فريد. وكلّ صفٍّ يحقّق القديمَ يحقّق الجديد (المفتاح وحده فريد ⇒ الزوج فريد)، فلا
-- يفشل الإنشاء على بياناتٍ قائمة. وصفوفُ tenant_id IS NULL لا تتصادم (NULL ليس مساوياً)، وهي
-- لا تُكتَب من الراوتر الذي يأخذ المستأجِر من التوكن دائماً.
-- (v238–v240 محجوزةٌ لمسوّداتٍ محلّيّةٍ معلّقة لم تُسجَّل بعد.)

-- **الاسمُ يبقى `uq_edge_idempotency`** (مراجعة Copilot على #1342): المُهاجِر يُعيد تشغيل MANIFEST
-- كاملاً في كلّ دورة (`migrations/apply_in_compose.sh`، `scripts_v9/run_migrations.sql`)، فيُعاد
-- v9 قبل v241. لو حمل الفهرسُ الجديد اسماً آخر لأعاد v9 إنشاءَ الفهرس العالميّ بـ`IF NOT EXISTS`،
-- ففشل بانتهاك تفرّدٍ ما إن يتشارك مستأجِران مفتاحاً — أي بعد أوّل استعمالٍ صحيحٍ لهذه الهجرة.
-- فيُحوَّل الفهرسُ في مكانه تحت الاسم نفسه، فيصير `CREATE UNIQUE INDEX IF NOT EXISTS
-- uq_edge_idempotency` في v9 لا-عملاً في كلّ إعادة. والتحويلُ نفسُه متساوي القوّة: فهرسٌ بعمودين
-- قائمٌ ⇒ لا شيء. الترتيب داخل المعاملة: يُنشأ الجديد باسمٍ مؤقّت، ثمّ يُحذف القديم، ثمّ يُعاد
-- تسميته — فلا تمرّ لحظةٌ بلا فهرسٍ فريد. ويُلتقَط أيضاً اسمُ المسوّدة المحلّيّة السابقة
-- `uq_edge_idempotency_tenant` إن وُجد.
DO $$
DECLARE
    v_cols int;
BEGIN
    SELECT i.indnatts INTO v_cols
      FROM pg_index i
      JOIN pg_class c ON c.oid = i.indexrelid
     WHERE c.relname = 'uq_edge_idempotency'
       AND c.relnamespace = 'public'::regnamespace;

    IF v_cols = 2 THEN
        RETURN;  -- مُحوَّلٌ سلفاً (إعادة تشغيل MANIFEST)
    END IF;

    CREATE UNIQUE INDEX IF NOT EXISTS uq_edge_idempotency_tenant
        ON edge_results (tenant_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL;

    DROP INDEX IF EXISTS uq_edge_idempotency;

    ALTER INDEX uq_edge_idempotency_tenant RENAME TO uq_edge_idempotency;
END $$;
