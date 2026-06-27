-- Phase 11 Federated Multi-Agent Autonomous Operations
-- Stores agent proposals, consensus decisions, operation plans, and safe experiments.

CREATE TABLE IF NOT EXISTS agent_federation_cycles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id UUID,
    cycle_id TEXT NOT NULL UNIQUE,
    objective TEXT NOT NULL,
    context_id TEXT NOT NULL,
    consensus_status TEXT NOT NULL,
    selected_action TEXT,
    dispatch_ready BOOLEAN NOT NULL DEFAULT FALSE,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_federation_cycles_tenant_field_created
    ON agent_federation_cycles (tenant_id, field_id, created_at DESC);

CREATE TABLE IF NOT EXISTS agent_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    cycle_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL UNIQUE,
    agent_role TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    priority INTEGER NOT NULL DEFAULT 0,
    safety_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_proposals_cycle_role
    ON agent_proposals (cycle_id, agent_role);

CREATE TABLE IF NOT EXISTS federated_policy_experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    experiment_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('shadow','canary','champion_challenger')),
    objective TEXT NOT NULL,
    champion_policy TEXT NOT NULL,
    challenger_policy TEXT NOT NULL,
    traffic_split JSONB NOT NULL DEFAULT '{}'::jsonb,
    guardrails JSONB NOT NULL DEFAULT '{}'::jsonb,
    promotion_metrics JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agent_federation_cycles ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE federated_policy_experiments ENABLE ROW LEVEL SECURITY;

-- FORCE صريح: جداول مُنشأة بعد propagate (v70)؛ بلا FORCE يتجاوزها مالك الجدول.
-- (WITH CHECK يُضيفه v122 الأخير لسياسات الكتابة USING-only.)
ALTER TABLE agent_federation_cycles FORCE ROW LEVEL SECURITY;
ALTER TABLE agent_proposals FORCE ROW LEVEL SECURITY;
ALTER TABLE federated_policy_experiments FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY agent_federation_cycles_tenant_isolation ON agent_federation_cycles
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY agent_proposals_tenant_isolation ON agent_proposals
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
    CREATE POLICY federated_policy_experiments_tenant_isolation ON federated_policy_experiments
        USING (tenant_id::text = current_setting('app.tenant_id', true));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
