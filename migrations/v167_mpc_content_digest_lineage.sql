-- v167_mpc_content_digest_lineage.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- نَسَب عديم التصادم عبر سلسلة القرار: يجعل content_digest (sha256 كامل، 64-hex)
-- **عموداً أوّليّاً مفهرَساً** على جداول السلسلة، بدل الاكتفاء بـcandidate_lineage_id
-- (16-hex، أعلى تصادماً) أو دفنه في decision_value JSONB.
--
-- السياق (تدقيق P0-P1 + شهادة البيئة الحيّة، المرحلة 4): فصلنا سابقاً content_digest
-- (المحتوى) عن candidate_lineage_id (العرض) عن idempotency_key (الفتحة). لكن السلسلة
-- كانت تُنتشِر النَّسَب بـcandidate_lineage_id فقط؛ الشهادة الحيّة كشفت أنّ الـdigest
-- الكامل غير قابل للاستعلام/الفهرسة عبر الجداول. هذه الهجرة تُغلق تلك الفجوة.
--
-- إضافيّة ومتوافقة للخلف: أعمدة NULL-able (لا تكسر صفوفاً قائمة). التوصيل في
-- decision-service/persistence.py يملؤها من الرأس (decision_record) ويُنتشِرها للحلقات
-- الأدنى بالبحث عبر decision_id. idempotent (ADD COLUMN/INDEX IF NOT EXISTS).
-- ─────────────────────────────────────────────────────────────────────────────

-- رأس السلسلة: القرار/المرشّح (v78). content_digest يُستخرَج من decision_value.
ALTER TABLE decision_record       ADD COLUMN IF NOT EXISTS content_digest TEXT;
-- تنفيذ الإرسال (v66) — يُنتشَر من decision_record عبر recommendation_id.
ALTER TABLE dispatch_decisions    ADD COLUMN IF NOT EXISTS content_digest TEXT;
-- النتيجة (v79) — يُنتشَر من decision_record عبر decision_id.
ALTER TABLE outcome_record        ADD COLUMN IF NOT EXISTS content_digest TEXT;
-- نتيجة التوصية (v49) — يُنتشَر من decision_record عبر decision_id.
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS content_digest TEXT;

-- فهارس التتبّع بالبصمة الكاملة (مُقيَّدة بالمستأجِر — تتّسق مع RLS).
CREATE INDEX IF NOT EXISTS idx_decision_record_content_digest
    ON decision_record (tenant_id, content_digest);
CREATE INDEX IF NOT EXISTS idx_dispatch_decisions_content_digest
    ON dispatch_decisions (tenant_id, content_digest);
CREATE INDEX IF NOT EXISTS idx_outcome_record_content_digest
    ON outcome_record (tenant_id, content_digest);
CREATE INDEX IF NOT EXISTS idx_recommendation_outcomes_content_digest
    ON recommendation_outcomes (tenant_id, content_digest);

COMMENT ON COLUMN decision_record.content_digest IS
    'sha256 كامل (64-hex) على canonical-JSON لكلّ حقائق القرار — نَسَب عديم التصادم يُنتشَر عبر السلسلة (v167). NULL للصفوف السابقة أو مصادر بلا digest.';
