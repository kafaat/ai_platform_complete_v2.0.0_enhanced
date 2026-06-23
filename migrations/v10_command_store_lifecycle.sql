-- migrations/v10_command_store_lifecycle.sql
--
-- v10: Command Store (server-side idempotency) + Field Lifecycle
--
-- المرجع:
--   - syncEngine.ts (mobile side) → نظيره هنا على الـserver
--   - دراسة المراجعة المعماريّة الخارجيّة (تكييف غير حرفيّ)
--
-- المبادئ:
--   - command_id (UUID) = هويّة عبر الـclient + server
--   - status: pending|processing|succeeded|failed
--   - duplicate POST بنفس command_id → الـserver يُرجع الـcached result
--   - lifecycle stage machine: invalid transitions تُرفَض في الـDB

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- ١. Command Store (Idempotency Backbone)
-- ════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS commands (
    command_id      UUID PRIMARY KEY,
    command_type    TEXT NOT NULL,            -- e.g. "field.create", "operation.harvest.complete"
    actor_id        TEXT NOT NULL,            -- user_id
    tenant_id       UUID NOT NULL,            -- multi-tenant isolation
    payload         JSONB NOT NULL,
    source          TEXT NOT NULL CHECK (source IN ('mobile', 'web', 'edge', 'scheduler')),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'succeeded', 'failed')),
    result          JSONB,
    error           TEXT,
    retry_count     INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_commands_actor_status   ON commands(actor_id, status);
CREATE INDEX IF NOT EXISTS idx_commands_tenant_created ON commands(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_commands_status         ON commands(status) WHERE status IN ('pending', 'processing');

-- RLS — tenant isolation على الـcommands
ALTER TABLE commands ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS commands_tenant_isolation ON commands;  -- idempotency (المُشغِّل يُعيد التطبيق كلّ إقلاع)
CREATE POLICY commands_tenant_isolation ON commands
    USING (
        -- fail-closed: لو app.current_tenant غير مضبوط (NULL) → لا صفوف
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    );

-- Trigger: updated_at تلقائي
CREATE OR REPLACE FUNCTION trg_commands_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    IF NEW.status IN ('succeeded', 'failed') AND OLD.status NOT IN ('succeeded', 'failed') THEN
        NEW.completed_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS commands_updated_at ON commands;
CREATE OR REPLACE TRIGGER commands_updated_at BEFORE UPDATE ON commands
    FOR EACH ROW EXECUTE FUNCTION trg_commands_updated_at();


-- ════════════════════════════════════════════════════════════════
-- ٢. Field Lifecycle State Machine
-- ════════════════════════════════════════════════════════════════
-- Stages: CREATED → PREPARED → PLANTED → GROWING → MATURE → HARVESTED → POST_HARVEST
-- valid transitions enforced via CHECK + trigger

DO $$ BEGIN
    CREATE TYPE field_lifecycle_stage AS ENUM (
        'CREATED',       -- الحقل أُنشئ، لا موسم بعد
        'PREPARED',      -- تربة جُهِّزت (حراثة، تسوية)
        'PLANTED',       -- بُذِر
        'GROWING',       -- في النموّ النشط
        'MATURE',        -- نضج، جاهز للحصاد
        'HARVESTED',     -- حُصِد
        'POST_HARVEST'   -- ما بعد الحصاد (TrueUp / تحليل)
    );
EXCEPTION WHEN duplicate_object THEN null;
END $$;

-- جدول الـlifecycle (واحد لكل (field, season))
CREATE TABLE IF NOT EXISTS field_lifecycle (
    lifecycle_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    field_id           UUID NOT NULL,
    tenant_id          UUID NOT NULL,
    season_id          UUID,                 -- nullable حتّى البذر
    current_stage      field_lifecycle_stage NOT NULL DEFAULT 'CREATED',
    stage_entered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(field_id, season_id)
);

CREATE INDEX IF NOT EXISTS idx_field_lifecycle_field ON field_lifecycle(field_id);
CREATE INDEX IF NOT EXISTS idx_field_lifecycle_stage ON field_lifecycle(current_stage, stage_entered_at);

ALTER TABLE field_lifecycle ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS field_lifecycle_tenant_isolation ON field_lifecycle;  -- idempotency
CREATE POLICY field_lifecycle_tenant_isolation ON field_lifecycle
    USING (
        -- fail-closed: لو app.current_tenant غير مضبوط (NULL) → لا صفوف
        tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
    );

-- تاريخ الانتقالات (immutable audit log)
CREATE TABLE IF NOT EXISTS field_lifecycle_transitions (
    transition_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lifecycle_id    UUID NOT NULL REFERENCES field_lifecycle(lifecycle_id),
    from_stage      field_lifecycle_stage,
    to_stage        field_lifecycle_stage NOT NULL,
    transitioned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by      TEXT NOT NULL,
    command_id      UUID REFERENCES commands(command_id),  -- لربط الانتقال بـCommand
    reason          TEXT
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_transitions_lifecycle
    ON field_lifecycle_transitions(lifecycle_id, transitioned_at);

-- ════════════════════════════════════════════════════════════════
-- ٣. Function: valid_transition (enforces state machine)
-- ════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION valid_lifecycle_transition(
    p_from field_lifecycle_stage,
    p_to   field_lifecycle_stage
) RETURNS BOOLEAN AS $$
BEGIN
    -- الانتقالات المسموحة
    RETURN CASE
        WHEN p_from = 'CREATED'      AND p_to = 'PREPARED'     THEN TRUE
        WHEN p_from = 'PREPARED'     AND p_to = 'PLANTED'      THEN TRUE
        WHEN p_from = 'PLANTED'      AND p_to = 'GROWING'      THEN TRUE
        WHEN p_from = 'GROWING'      AND p_to = 'MATURE'       THEN TRUE
        WHEN p_from = 'MATURE'       AND p_to = 'HARVESTED'    THEN TRUE
        WHEN p_from = 'HARVESTED'    AND p_to = 'POST_HARVEST' THEN TRUE
        -- إعادة دورة (موسم جديد): POST_HARVEST → PREPARED
        WHEN p_from = 'POST_HARVEST' AND p_to = 'PREPARED'     THEN TRUE
        -- نفس الـstage (idempotent re-transition) — مرفوض، يجب تجاوزه قبل المحاولة
        WHEN p_from = p_to                                      THEN FALSE
        ELSE FALSE
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Trigger: validates lifecycle transitions BEFORE INSERT
CREATE OR REPLACE FUNCTION trg_validate_lifecycle_transition() RETURNS trigger AS $$
DECLARE
    v_current_stage field_lifecycle_stage;
BEGIN
    SELECT current_stage INTO v_current_stage
    FROM field_lifecycle WHERE lifecycle_id = NEW.lifecycle_id;

    IF v_current_stage IS NULL THEN
        RAISE EXCEPTION 'lifecycle_id % not found', NEW.lifecycle_id;
    END IF;

    -- Check valid transition
    IF NOT valid_lifecycle_transition(v_current_stage, NEW.to_stage) THEN
        RAISE EXCEPTION 'Invalid lifecycle transition: % → %',
            v_current_stage, NEW.to_stage
            USING HINT = 'Check field_lifecycle.current_stage and ensure transition is allowed.';
    END IF;

    NEW.from_stage := v_current_stage;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS validate_lifecycle_transition ON field_lifecycle_transitions;
CREATE OR REPLACE TRIGGER validate_lifecycle_transition BEFORE INSERT ON field_lifecycle_transitions
    FOR EACH ROW EXECUTE FUNCTION trg_validate_lifecycle_transition();

-- Trigger: عند INSERT في transitions → update الـcurrent_stage
CREATE OR REPLACE FUNCTION trg_apply_lifecycle_transition() RETURNS trigger AS $$
BEGIN
    UPDATE field_lifecycle
    SET current_stage = NEW.to_stage,
        stage_entered_at = NEW.transitioned_at
    WHERE lifecycle_id = NEW.lifecycle_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS apply_lifecycle_transition ON field_lifecycle_transitions;
CREATE OR REPLACE TRIGGER apply_lifecycle_transition AFTER INSERT ON field_lifecycle_transitions
    FOR EACH ROW EXECUTE FUNCTION trg_apply_lifecycle_transition();

COMMIT;

-- Verification queries:
-- SELECT valid_lifecycle_transition('CREATED', 'PLANTED');  -- FALSE (يجب أن يمرّ بـPREPARED)
-- SELECT valid_lifecycle_transition('GROWING', 'MATURE');   -- TRUE
-- SELECT valid_lifecycle_transition('CREATED', 'HARVESTED'); -- FALSE
