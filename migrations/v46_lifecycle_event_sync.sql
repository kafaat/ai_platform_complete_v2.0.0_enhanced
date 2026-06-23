-- migrations/v46_lifecycle_event_sync.sql
--
-- v46: مزامنة دورة الحياة ↔ سجلّ الأحداث (Lifecycle ↔ Events Sync)
--
-- الثغرة المُغلَقة (state drift):
--   جدول field_lifecycle_transitions (v10) هو سجلّ الانتقالات، وجدول events
--   (v11) هو "نظام السجلّ" للأحداث. لكنّ كتابة الانتقال لم تكن تُولِّد حدثاً
--   مطلقاً: لا FieldLifecycleEngine.transition() (api/field_lifecycle.py) ولا
--   أيّ مسار كتابة آخر يستدعي emit_event بنوع 'lifecycle.transitioned'.
--   النتيجة: المستهلكون (event_replay / field_timeline / event_upcasting)
--   يتوقّعون أحداث 'lifecycle.transitioned'، لكنّ السجلّ لا يحوي أيّاً منها
--   ⇒ انحراف بين آلة الحالة وسجلّ الأحداث (lifecycle ↔ events drift).
--
-- الحلّ (DB-level، يلتقط كلّ مسارات الكتابة):
--   trigger بعد INSERT على field_lifecycle_transitions يستدعي emit_event
--   (v11/v18). الـtrigger مستقلّ عن مسار الكتابة (Python / SQL يدويّ / استيراد)
--   فكلّ انتقال — أيّاً كان مصدره — يُصدِر حدثه المقابل. emit_event نفسه
--   idempotent (dedup_key) فلا أحداث مكرّرة.
--
-- ملاحظة بنيويّة: field_lifecycle_transitions لا يحوي tenant_id ولا field_id
--   مباشرةً (v10 lines 109-118) — كلاهما على field_lifecycle، فنجلبهما بالـJOIN
--   على lifecycle_id. entity_id يُمرَّر نصّاً (events.entity_id TEXT منذ v18)
--   من field_lifecycle.field_id (TEXT منذ v18). occurred_at نستخدم العمود
--   المضاف في v9_lifecycle_occurred_at مع COALESCE إلى transitioned_at.

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- Trigger function: emit a 'lifecycle.transitioned' event per transition
-- ════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION trg_lifecycle_transition_emit_event() RETURNS trigger AS $$
DECLARE
    v_field_id   TEXT;
    v_tenant_id  UUID;
    v_season_id  UUID;
BEGIN
    -- field_id + tenant_id يقيمان على field_lifecycle لا على الانتقال نفسه.
    SELECT fl.field_id, fl.tenant_id, fl.season_id
      INTO v_field_id, v_tenant_id, v_season_id
      FROM field_lifecycle fl
     WHERE fl.lifecycle_id = NEW.lifecycle_id;

    -- دفاعيّاً: لو لم يوجد سجلّ lifecycle (لا يُفترَض — FK محذوف نظريّاً)،
    -- لا نُصدِر حدثاً بـtenant_id NULL (events.tenant_id NOT NULL).
    IF v_tenant_id IS NULL THEN
        RETURN NEW;
    END IF;

    PERFORM emit_event(
        p_event_type  => 'lifecycle.transitioned',
        p_entity_type => 'field',
        p_entity_id   => v_field_id,                       -- TEXT (events.entity_id TEXT منذ v18)
        p_tenant_id   => v_tenant_id,
        p_payload     => jsonb_build_object(
            'lifecycle_id',  NEW.lifecycle_id,
            'transition_id', NEW.transition_id,
            'field_id',      v_field_id,
            'season_id',     v_season_id,
            'from_stage',    NEW.from_stage,                -- مضبوطة بالـtrigger BEFORE INSERT (v10)
            'to_stage',      NEW.to_stage,
            'reason',        NEW.reason,
            'command_id',    NEW.command_id,
            'occurred_at',   COALESCE(NEW.occurred_at, NEW.transitioned_at)
        ),
        p_source      => 'system',
        p_actor_id    => NEW.changed_by,                   -- changed_by NOT NULL (v10)
        p_command_id  => NEW.command_id,                   -- nullable (v10)
        p_occurred_at => COALESCE(NEW.occurred_at, NEW.transitioned_at)
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- idempotent: نُسقِط ثمّ نُنشئ (لا overload / لا تكرار عند إعادة التطبيق)
DROP TRIGGER IF EXISTS lifecycle_transition_emit_event ON field_lifecycle_transitions;
CREATE OR REPLACE TRIGGER lifecycle_transition_emit_event
    AFTER INSERT ON field_lifecycle_transitions
    FOR EACH ROW EXECUTE FUNCTION trg_lifecycle_transition_emit_event();

COMMIT;

-- ════════════════════════════════════════════════════════════════
-- Verification:
--   -- بعد أيّ انتقال صالح:
--   --   INSERT INTO field_lifecycle_transitions
--   --       (lifecycle_id, to_stage, changed_by) VALUES (<id>, 'PREPARED', 'u1');
--   -- يجب أن يظهر حدث مقابل:
--   SELECT event_type, entity_type, entity_id, payload->>'to_stage'
--     FROM events WHERE event_type = 'lifecycle.transitioned'
--     ORDER BY occurred_at DESC LIMIT 1;
--   -- وصفّ outbox مقابل (emit_event يكتب outbox):
--   SELECT * FROM event_outbox WHERE nats_subject = 'sahool.events.lifecycle.transitioned';
-- ════════════════════════════════════════════════════════════════
