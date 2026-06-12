-- v48: (1) FK صلب Activity→Season (يُغلق فجوة «العلاقة تطبيقيّة لا قاعديّة»).
--      (2) حوكمة الأحداث الفاشلة (DLQ): عرض + دوالّ إعادة جدولة لـoutbox الفاشل.
-- كلّها idempotent + آمنة على البيانات القائمة (NOT VALID / IF NOT EXISTS).

-- ── (1) Activity → Season FK ─────────────────────────────────────
-- season_id اختياريّ (nullable)؛ FK بعمود واحد + ON DELETE SET NULL: عند حذف
-- موسم تُفصَل العمليّة (season_id=NULL) لا تُحذف. NOT VALID لأمان الصفوف القائمة.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_activities_season') THEN
        ALTER TABLE activities ADD CONSTRAINT fk_activities_season
            FOREIGN KEY (season_id) REFERENCES seasons (season_id)
            ON DELETE SET NULL NOT VALID;
    END IF;
END $$;

-- ── (2) DLQ — حوكمة الأحداث الفاشلة في event_outbox ──────────────
-- عرض يُبرز الأحداث الميّتة (status='failed' بعد استنفاد المحاولات) + تفاصيلها
-- لمراقبتها/تشخيصها بدل ضياعها صامتةً.
CREATE OR REPLACE VIEW v_event_dead_letter AS
SELECT o.outbox_id, o.event_id, o.nats_subject, o.retry_count,
       o.last_error, o.last_attempt_at, o.created_at,
       e.event_type, e.entity_type, e.entity_id, e.tenant_id, e.occurred_at
FROM event_outbox o
JOIN events e ON e.event_id = o.event_id
WHERE o.status = 'failed';

-- إعادة جدولة حدث ميّت واحد (بعد إصلاح السبب) → pending + تصفير العدّاد.
CREATE OR REPLACE FUNCTION requeue_dead_letter(p_outbox_id BIGINT) RETURNS BOOLEAN AS $$
DECLARE v_n INTEGER;
BEGIN
    UPDATE event_outbox
       SET status = 'pending', retry_count = 0, last_error = NULL
     WHERE outbox_id = p_outbox_id AND status = 'failed';
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n > 0;
END;
$$ LANGUAGE plpgsql;

-- إعادة جدولة كلّ الأحداث الميّتة (تشغيل ops بعد إصلاح NATS مثلاً) → عددها.
CREATE OR REPLACE FUNCTION requeue_all_dead_letter() RETURNS INTEGER AS $$
DECLARE v_n INTEGER;
BEGIN
    UPDATE event_outbox
       SET status = 'pending', retry_count = 0, last_error = NULL
     WHERE status = 'failed';
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END;
$$ LANGUAGE plpgsql;
