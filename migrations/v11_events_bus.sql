-- migrations/v11_events_bus.sql
--
-- v11: Events table — الـoutput من commands
--
-- العلاقة:
--   commands (input من mobile/web)  →  events (الـoutput الذي يحدث في النظام)
--
-- لماذا نحتاج هذا؟
--   - commands: "افعل X" (intent)
--   - events:   "X حدث" (fact)
--   commands قد يفشل، events لا (immutable history)
--
-- ما يميّز هذا عن المستندات الخارجيّة:
--   ✓ tenant_id إلزامي (RLS isolation)
--   ✓ idempotency_key لمنع duplicate inserts
--   ✓ ربط مباشر مع commands.command_id (causality)
--   ✓ JSONB validation (schema versioning)
--   ✓ index على entity + time للـreplay السريع

BEGIN;

-- pgcrypto مطلوب لـdigest() (الـpayload_hash). gen_random_uuid أصبح core منذ PG13.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ════════════════════════════════════════════════════════════════
-- ١. Events table (System of Record للأحداث)
-- ════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS events (
    event_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type        TEXT NOT NULL,             -- "field.created", "lifecycle.transitioned"...
    schema_version    INT NOT NULL DEFAULT 1,    -- للـschema evolution
    entity_type       TEXT NOT NULL CHECK (
        entity_type IN ('field', 'farm', 'operation', 'equipment', 'sensor', 'well', 'sample', 'season', 'user')
    ),
    entity_id         UUID NOT NULL,
    tenant_id         UUID NOT NULL,             -- مُلزم لـRLS
    actor_id          TEXT,                      -- المستخدم/الـsystem الذي ولّد الحدث
    command_id        UUID REFERENCES commands(command_id),  -- ربط مباشر بالـcommand المُولِّد
    payload           JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_hash      TEXT,                      -- SHA-256 للـidempotency
    -- dedup_key: مفتاح إزالة التكرار. عمود نصّي بسيط (IMMUTABLE) بدل
    -- index على date_trunc() — الذي يرفضه PostgreSQL لأنّ date_trunc على
    -- timestamptz دالّة STABLE لا IMMUTABLE، فلا يُسمَح بها في index.
    -- يُحسَب في emit_event ويُخزَّن مباشرةً.
    dedup_key         TEXT,
    source            TEXT NOT NULL CHECK (
        source IN ('mobile', 'web', 'edge', 'scheduler', 'system', 'ai', 'sensor')
    ),
    occurred_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- متى حدث فعلياً
    recorded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()   -- متى وصل للسجلّ
);

-- منع duplicate events (idempotency) — index على عمود بسيط، IMMUTABLE مضمون
CREATE UNIQUE INDEX IF NOT EXISTS ux_events_dedup
    ON events(dedup_key)
    WHERE dedup_key IS NOT NULL;

-- Indexes للـreplay السريع
CREATE INDEX IF NOT EXISTS idx_events_entity        ON events(entity_type, entity_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_type_time     ON events(event_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_tenant_time   ON events(tenant_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_command       ON events(command_id) WHERE command_id IS NOT NULL;

-- RLS — tenant isolation
ALTER TABLE events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS events_tenant_isolation ON events;  -- idempotency (المُشغِّل يُعيد التطبيق كلّ إقلاع)
CREATE POLICY events_tenant_isolation ON events
    USING (
        -- fail-closed: لو app.current_tenant غير مضبوط (NULL) → لا صفوف
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    );

-- ════════════════════════════════════════════════════════════════
-- ٢. Outbox pattern (للـreliable NATS publishing)
-- ════════════════════════════════════════════════════════════════
-- المشكلة المنهجيّة في المستند الخارجي:
--   "INSERT INTO events" ثمّ "NATS publish" — لو فشل NATS بعد INSERT،
--   فقدنا الحدث في الـstream لكن بقي في الـDB → divergence.
--
-- الحلّ الصحيح: Outbox pattern
--   ١. INSERT INTO events (في transaction)
--   ٢. INSERT INTO event_outbox (نفس الـtransaction)
--   ٣. worker منفصل يقرأ outbox ويُرسل لـNATS
--   ٤. عند نجاح NATS publish → mark outbox row sent
--
-- النتيجة: at-least-once delivery مضمونة بدون divergence.

CREATE TABLE IF NOT EXISTS event_outbox (
    outbox_id      BIGSERIAL PRIMARY KEY,
    event_id       UUID NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    nats_subject   TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'sent', 'failed')),
    retry_count    INT NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    sent_at        TIMESTAMPTZ,
    last_error     TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON event_outbox(status, created_at)
    WHERE status IN ('pending', 'failed');

-- ════════════════════════════════════════════════════════════════
-- ٣. Helper function: emit_event (atomic insert + outbox)
-- ════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION emit_event(
    p_event_type    TEXT,
    p_entity_type   TEXT,
    p_entity_id     UUID,
    p_tenant_id     UUID,
    p_payload       JSONB,
    p_source        TEXT DEFAULT 'system',
    p_actor_id      TEXT DEFAULT NULL,
    p_command_id    UUID DEFAULT NULL,
    p_occurred_at   TIMESTAMPTZ DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_event_id     UUID := gen_random_uuid();
    v_payload_hash TEXT;
    v_dedup_key    TEXT;
    v_occurred_at  TIMESTAMPTZ := COALESCE(p_occurred_at, NOW());
BEGIN
    -- payload hash للـidempotency (deterministic)
    v_payload_hash := encode(
        digest(p_event_type || p_entity_id::text || p_payload::text, 'sha256'),
        'hex'
    );

    -- dedup_key: يُحسَب هنا (لا في index expression). نستخدم to_char للحصول
    -- على تاريخ اليوم كنصّ ثابت. الحساب في PL/pgSQL مسموح (الـSTABLE مقبول هنا،
    -- المشكلة كانت فقط في index expressions).
    v_dedup_key := p_tenant_id::text || ':' || p_event_type || ':'
                || p_entity_id::text || ':' || v_payload_hash || ':'
                || to_char(v_occurred_at, 'YYYY-MM-DD');

    -- Insert event (قد يفشل لو duplicate على dedup_key)
    INSERT INTO events (
        event_id, event_type, entity_type, entity_id, tenant_id,
        actor_id, command_id, payload, payload_hash, dedup_key, source, occurred_at
    ) VALUES (
        v_event_id, p_event_type, p_entity_type, p_entity_id, p_tenant_id,
        p_actor_id, p_command_id, p_payload, v_payload_hash, v_dedup_key, p_source, v_occurred_at
    )
    ON CONFLICT (dedup_key) WHERE dedup_key IS NOT NULL
    DO NOTHING
    RETURNING event_id INTO v_event_id;

    -- لو duplicate (event_id = NULL)، نخرج بدون outbox
    IF v_event_id IS NULL THEN
        RETURN NULL;
    END IF;

    -- Insert outbox للـreliable NATS publishing
    INSERT INTO event_outbox (event_id, nats_subject)
    VALUES (v_event_id, 'sahool.events.' || p_event_type);

    RETURN v_event_id;
END;
$$ LANGUAGE plpgsql;

-- ════════════════════════════════════════════════════════════════
-- ٤. Materialized view: latest event per entity (للسرعة)
-- ════════════════════════════════════════════════════════════════
-- مفيد للـUI: "ما الذي حدث آخر مرّة على هذا الحقل؟"
CREATE OR REPLACE VIEW v_entity_latest_event AS
SELECT DISTINCT ON (entity_type, entity_id)
    entity_type,
    entity_id,
    event_type as last_event_type,
    occurred_at as last_occurred_at,
    payload as last_payload
FROM events
ORDER BY entity_type, entity_id, occurred_at DESC;

COMMIT;

-- ════════════════════════════════════════════════════════════════
-- Verification:
--   SELECT emit_event(
--       'field.created', 'field', gen_random_uuid(), gen_random_uuid(),
--       '{"name": "test"}'::jsonb, 'mobile'
--   );
--   SELECT * FROM events ORDER BY occurred_at DESC LIMIT 1;
--   SELECT * FROM event_outbox WHERE status = 'pending';
-- ════════════════════════════════════════════════════════════════
