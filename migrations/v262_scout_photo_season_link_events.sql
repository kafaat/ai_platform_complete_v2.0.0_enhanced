-- v262: explicit, correctable photo -> ACCEPTED season links, owned by scout-ingest.
-- ════════════════════════════════════════════════════════════════════════
-- Owner delivery «photo season link, phase 5» (its v257, renumbered: v257-v261 are taken on
-- other branches). Never infer a link from crop, date, polygon overlap or AI output. An immutable
-- succession of events (link / revoke, each revision naming its predecessor and a reason) keeps
-- the history. Composite tenant+field+pin and tenant+field+season FKs fence foreign identifiers.
--
-- Requires v201 (season_records) and v260 (scout_photo_evidence). Idempotent on a re-applied
-- MANIFEST (IF NOT EXISTS, DROP … IF EXISTS, CREATE OR REPLACE). Grants to sahool_ingest
-- (SELECT, INSERT; no UPDATE/DELETE) are in bootstrap_postgres.sh and apply_in_compose.sh.
-- The API is media_api.py behind SCOUT_MEDIA_SEASON_LINK_ENABLED (default 0).
BEGIN;
SET LOCAL lock_timeout = '15s';

-- The season itself belongs to scout-ingest; the composite key prevents a
-- photo from being linked to a season of another field in the same tenant.
CREATE UNIQUE INDEX IF NOT EXISTS season_records_id_tenant_field_uq
    ON season_records (id, tenant_id, field_id);

CREATE TABLE IF NOT EXISTS scout_photo_season_link_events (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id TEXT NOT NULL,
    pin_id TEXT NOT NULL,
    season_id UUID,
    action TEXT NOT NULL CHECK (action IN ('link', 'revoke')),
    previous_event_id UUID,
    actor_id TEXT NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 200),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT scout_photo_season_event_action_ck CHECK (
        (action = 'link' AND season_id IS NOT NULL)
        OR (action = 'revoke' AND season_id IS NULL AND reason IS NOT NULL AND length(btrim(reason)) BETWEEN 1 AND 2000)
    ),
    CONSTRAINT scout_photo_season_event_revision_ck CHECK (
        previous_event_id IS NULL OR (previous_event_id <> event_id AND reason IS NOT NULL AND length(btrim(reason)) BETWEEN 1 AND 2000)
    ),
    CONSTRAINT scout_photo_season_event_pin_fk FOREIGN KEY (tenant_id, field_id, pin_id)
        REFERENCES scout_photo_evidence (tenant_id, field_id, pin_id),
    CONSTRAINT scout_photo_season_event_season_fk FOREIGN KEY (season_id, tenant_id, field_id)
        REFERENCES season_records (id, tenant_id, field_id),
    CONSTRAINT scout_photo_season_event_scope_uq UNIQUE (event_id, tenant_id, field_id, pin_id),
    CONSTRAINT scout_photo_season_event_prev_fk
        FOREIGN KEY (previous_event_id, tenant_id, field_id, pin_id)
        REFERENCES scout_photo_season_link_events (event_id, tenant_id, field_id, pin_id),
    -- Exactly one next event may supersede a previous event. This is the
    -- concurrency fence even when two API requests read the same old head.
    CONSTRAINT scout_photo_season_event_successor_uq UNIQUE (previous_event_id)
);
-- Exactly one root per photo, but revisions remain possible with explicit
-- previous_event_id. The read model rejects multiple heads on schema drift.
CREATE UNIQUE INDEX IF NOT EXISTS scout_photo_season_event_root_uq
    ON scout_photo_season_link_events (tenant_id, field_id, pin_id)
    WHERE previous_event_id IS NULL;
CREATE INDEX IF NOT EXISTS scout_photo_season_event_field_idx
    ON scout_photo_season_link_events (tenant_id, field_id, pin_id, created_at DESC);

ALTER TABLE scout_photo_season_link_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE scout_photo_season_link_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS scout_photo_season_events_tenant ON scout_photo_season_link_events;
CREATE POLICY scout_photo_season_events_tenant ON scout_photo_season_link_events
    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

CREATE OR REPLACE FUNCTION reject_scout_photo_season_event_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'scout_photo_season_link_event_immutable' USING ERRCODE = '55000';
END;
$$;
DROP TRIGGER IF EXISTS scout_photo_season_link_event_immutable_guard
    ON scout_photo_season_link_events;
CREATE TRIGGER scout_photo_season_link_event_immutable_guard
    BEFORE UPDATE OR DELETE ON scout_photo_season_link_events
    FOR EACH ROW EXECUTE FUNCTION reject_scout_photo_season_event_mutation();
REVOKE ALL ON scout_photo_season_link_events FROM PUBLIC;
COMMENT ON TABLE scout_photo_season_link_events IS
    'Explicit human-scoped season links; independent of disease diagnosis and decision authorization.';
COMMIT;
