-- Phase 11 federated-agent runtime hardening: reputation, conflict resolution, authority envelopes.

CREATE TABLE IF NOT EXISTS agent_reputation_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    agent_role TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL CHECK (score >= 0 AND score <= 1),
    sample_count INTEGER NOT NULL DEFAULT 0,
    safety_incident_count INTEGER NOT NULL DEFAULT 0,
    stale BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, agent_role)
);

CREATE TABLE IF NOT EXISTS agent_conflict_resolutions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id UUID NULL,
    cycle_id TEXT NULL,
    resolution_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    selected_action TEXT NULL,
    approval_required BOOLEAN NOT NULL DEFAULT TRUE,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    conflict_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    vetoes JSONB NOT NULL DEFAULT '[]'::jsonb,
    ranked_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_authority_envelopes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id UUID NULL,
    cycle_id TEXT NULL,
    envelope_id TEXT NOT NULL UNIQUE,
    allowed_authority TEXT NOT NULL,
    may_execute BOOLEAN NOT NULL DEFAULT FALSE,
    may_publish_event BOOLEAN NOT NULL DEFAULT FALSE,
    required_next_gate TEXT NOT NULL,
    blocked_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_reputation_tenant_role ON agent_reputation_scores (tenant_id, agent_role);
CREATE INDEX IF NOT EXISTS idx_agent_conflict_tenant_cycle ON agent_conflict_resolutions (tenant_id, cycle_id);
CREATE INDEX IF NOT EXISTS idx_agent_authority_tenant_cycle ON agent_authority_envelopes (tenant_id, cycle_id);

ALTER TABLE agent_reputation_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_conflict_resolutions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_authority_envelopes ENABLE ROW LEVEL SECURITY;

-- FORCE صريح: هذه الجداول مُنشأة بعد v9_rls_force_all/propagate (v70)، فلا
-- يطالها التعميم. بلا FORCE يتجاوز مالك الجدول (sahool_user) RLS تماماً.
-- (نظير _sahool_apply_tenant_rls الذي يطبّق ENABLE+FORCE+POLICY.)
ALTER TABLE agent_reputation_scores FORCE ROW LEVEL SECURITY;
ALTER TABLE agent_conflict_resolutions FORCE ROW LEVEL SECURITY;
ALTER TABLE agent_authority_envelopes FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_agent_reputation_policy ON agent_reputation_scores;
CREATE POLICY tenant_agent_reputation_policy ON agent_reputation_scores
    USING (tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_agent_conflict_policy ON agent_conflict_resolutions;
CREATE POLICY tenant_agent_conflict_policy ON agent_conflict_resolutions
    USING (tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_agent_authority_policy ON agent_authority_envelopes;
CREATE POLICY tenant_agent_authority_policy ON agent_authority_envelopes
    USING (tenant_id::text = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
