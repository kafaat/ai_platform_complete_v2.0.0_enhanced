-- SAHOOL v63 — migrations/v63_events_seq_deterministic_order.sql
-- ════════════════════════════════════════════════════════════════════
-- الفجوة (Projection Drift): إعادة بناء حالة الحقل تعتمد على
-- ‏`ORDER BY occurred_at ASC` وحده (event_bus.query_entity_history،
-- event_replay). لكنّ occurred_at هو TIMESTAMPTZ DEFAULT NOW()، فحدثان
-- في نفس اللحظة (نفس الميلّي/الميكرو ثانية — شائع في الكتابات الدفعيّة
-- والـsync) يصبح ترتيبهما **غير حتميّ**: يقرّره مُحسِّن PostgreSQL، فيختلف
-- بين إعادة بناء وأخرى ⇒ حالتان مختلفتان من نفس الأحداث = Projection Drift.
--
-- التعليق في v60 يعترف بهذا صراحةً:
--   "جدول events بلا عمود seq حاليّاً (v11) فيبقى NULL غالباً."
--
-- الحلّ: عمود seq تسلسليّ (BIGINT IDENTITY) — مؤشّر إدراج رتيب صارم
-- (monotonic) يكسر التعادل حتميّاً. الترتيب الحتميّ يصير (occurred_at, seq)،
-- وهو المفتاح المستعمل في إعادة البناء واللقطات والمؤشّرات.
--
-- لماذا IDENTITY لا BIGSERIAL: دلاليّاً متطابقان هنا، لكنّ IDENTITY معياريّ
-- (SQL standard) ويمنع الكتابة اليدويّة العرضيّة في seq (GENERATED ALWAYS).
-- ملاحظة: append-only store — seq يُسند عند الإدراج فقط، لا يتغيّر أبداً.
-- ════════════════════════════════════════════════════════════════════

BEGIN;

-- ① عمود seq التسلسليّ. GENERATED ALWAYS AS IDENTITY: يُسند آليّاً ولا
--    يُكتَب يدويّاً. الصفوف الموجودة تأخذ قيماً تصاعديّة فوريّة (PostgreSQL
--    يملأ IDENTITY للصفوف القائمة بترتيب فيزيائيّ — مقبول لأنّها تاريخ ثابت).
ALTER TABLE events
    ADD COLUMN IF NOT EXISTS seq BIGINT GENERATED ALWAYS AS IDENTITY;

-- ② فهرس الترتيب الحتميّ لإعادة البناء: (entity_type, entity_id, occurred_at, seq).
--    يطابق WHERE+ORDER BY في query_entity_history فيخدمه دون فرز إضافيّ.
CREATE INDEX IF NOT EXISTS idx_events_entity_replay_order
    ON events (entity_type, entity_id, occurred_at ASC, seq ASC);

-- ③ فهرس مساعد لمسار الأمر (command_id) المستعمل في timeline.
CREATE INDEX IF NOT EXISTS idx_events_command_seq
    ON events (command_id, occurred_at ASC, seq ASC)
    WHERE command_id IS NOT NULL;

COMMENT ON COLUMN events.seq IS
    'مؤشّر إدراج تسلسليّ صارم (monotonic، IDENTITY). يكسر تعادل occurred_at '
    'حتميّاً. مفتاح الترتيب الرسميّ لإعادة البناء = (occurred_at, seq). يسدّ '
    'فجوة Projection Drift التي اعترف بها تعليق v60. راجع v63.';

COMMIT;
