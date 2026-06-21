-- ════════════════════════════════════════════════════════════
-- SAHOOL v93 — processed_events: استهلاك outbox مُتعاضد (idempotent consumption)
-- ════════════════════════════════════════════════════════════
-- المشكلة: نمط الـoutbox يضمن تسليماً **at-least-once** (FOR UPDATE SKIP LOCKED +
-- النشر ثمّ وسم 'sent' في معاملة واحدة) — فالصفّ المنشور قبيل تعطّل قبل وسمه 'sent'
-- يُعاد نشره في الدورة التالية. مُستهلِك بلا حماية ⇒ أثر جانبيّ مزدوج (نشر مكرّر).
--
-- الحلّ: مخزن تعاضُد (idempotency keys) على مستوى الحدث. قبل تطبيق الأثر الجانبيّ،
-- يُطالِب المُستهلِك الحدثَ بإدراج (event_id) هنا داخل **نفس المعاملة** التي تُثبِّت
-- الأثر الجانبيّ. INSERT … ON CONFLICT DO NOTHING: إن أُدرِج الصفّ (rowcount=1) فهو
-- أوّل استهلاك ⇒ نُطبّق الأثر؛ وإن تعارض (rowcount=0) فقد عولِج سابقاً ⇒ نتخطّى.
-- الذرّيّة: المطالبة + الأثر في معاملة واحدة ⇒ تعطّل في المنتصف يُرجِع كليهما
-- (لا وسمٌ «معالَج» بلا إنجاز العمل).
--
-- ⚠️ عزل: هذا جدول بنية تحتيّة/مسك دفاتر (bookkeeping) على مستوى المنصّة، **لا**
-- مُنطّق بمستأجِر واحد — مرآةً لـevent_outbox/weather_grid/weather_forecasts العالميّة:
--   • لا عمود tenant_id (قصداً): المُستهلِك (OutboxWorker) عابر للمستأجرين بالتصميم
--     ويعمل على دور sahool_jobs (BYPASSRLS) عبر JOBS_DATABASE_URL. مفتاح التعاضُد هو
--     event_id (UUID فريد عالميّاً) — لا يحتاج تنطيقاً بمستأجِر.
--   • لذلك لا يلتقطه حارس test_rls_tenant_coverage (يفحص جداول tenant_id فقط)، ولا
--     RLS عليه — مطابقةً لطريقة معالجة جداول البنية التحتيّة العابرة الأخرى.
-- idempotent بالكامل (CREATE TABLE IF NOT EXISTS).

BEGIN;

CREATE TABLE IF NOT EXISTS processed_events (
    event_id     UUID         PRIMARY KEY,           -- مفتاح التعاضُد (فريد عالميّاً)
    processed_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    consumer     TEXT                                -- وسم المُستهِلك (مثل 'outbox_relay')
);

-- فهرس زمنيّ للتنظيف/التدقيق (إزالة الإدخالات القديمة دوريّاً لاحقاً إن لزم).
CREATE INDEX IF NOT EXISTS idx_processed_events_processed_at
    ON processed_events(processed_at);

COMMENT ON TABLE processed_events IS
    'مخزن تعاضُد استهلاك الأحداث (at-most-once): حدثٌ مُطالَب هنا = عولِج. عالميّ '
    'عمداً (لا tenant_id) — مُستهلِك outbox عابر للمستأجرين على دور sahool_jobs/BYPASSRLS.';
COMMENT ON COLUMN processed_events.event_id IS
    'معرّف الحدث (events.event_id) — PK يجعل INSERT … ON CONFLICT DO NOTHING حارسَ التعاضُد.';
COMMENT ON COLUMN processed_events.consumer IS
    'وسم المُستهلِك الذي طالَب الحدث (للتدقيق متعدّد المُستهلِكين).';

COMMIT;
