-- Phase 7 Enterprise GIS: collaboration, conformance, distributed raster, scenarios, autonomous recommendations.
-- Idempotent migration; runtime services may project these contracts into event streams and materialized views.

CREATE TABLE IF NOT EXISTS gis_collaboration_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    field_id UUID NOT NULL,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','committed','abandoned','expired')),
    base_revision INTEGER NOT NULL DEFAULT 0,
    current_revision INTEGER NOT NULL DEFAULT 0,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gis_collaboration_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    session_id UUID NOT NULL REFERENCES gis_collaboration_sessions(id) ON DELETE CASCADE,
    field_id UUID NOT NULL,
    user_id UUID,
    event_type TEXT NOT NULL CHECK (event_type IN ('presence','cursor','geometry_patch','annotation','commit','rollback')),
    revision INTEGER NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    conflict_policy TEXT NOT NULL DEFAULT 'revision_guard_then_merge',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gis_collab_events_session_rev ON gis_collaboration_events(session_id, revision, created_at);
CREATE INDEX IF NOT EXISTS idx_gis_collab_sessions_tenant_field ON gis_collaboration_sessions(tenant_id, field_id, status);

CREATE TABLE IF NOT EXISTS ogc_conformance_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID,
    service_url TEXT NOT NULL,
    conformance_classes TEXT[] NOT NULL DEFAULT '{}',
    team_engine_report_url TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','passed','failed','waived')),
    failures JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS distributed_raster_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    job_type TEXT NOT NULL CHECK (job_type IN ('scene_processing','tile_warm','statistics','mosaic','cog_overview','backfill')),
    runtime TEXT NOT NULL DEFAULT 'dask' CHECK (runtime IN ('dask','ray','celery','local')),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
    priority INTEGER NOT NULL DEFAULT 5,
    input JSONB NOT NULL DEFAULT '{}'::jsonb,
    output JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_distributed_raster_jobs_queue ON distributed_raster_jobs(status, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS idx_distributed_raster_jobs_tenant_type ON distributed_raster_jobs(tenant_id, job_type, status);

CREATE TABLE IF NOT EXISTS digital_twin_scenarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    farm_id UUID,
    name TEXT NOT NULL,
    baseline JSONB NOT NULL DEFAULT '{}'::jsonb,
    scenario JSONB NOT NULL DEFAULT '{}'::jsonb,
    projection JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autonomous_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    farm_id UUID,
    field_id UUID,
    domain TEXT NOT NULL,
    action TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('low','medium','high','critical')),
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    requires_human_approval BOOLEAN NOT NULL DEFAULT true,
    status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','approved','rejected','executed','expired')),
    rationale JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_autonomous_recommendations_queue ON autonomous_recommendations(tenant_id, status, priority, created_at);

ALTER TABLE gis_collaboration_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE gis_collaboration_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE ogc_conformance_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE distributed_raster_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE digital_twin_scenarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE autonomous_recommendations ENABLE ROW LEVEL SECURITY;

ALTER TABLE gis_collaboration_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE gis_collaboration_events FORCE ROW LEVEL SECURITY;
ALTER TABLE ogc_conformance_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE distributed_raster_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE digital_twin_scenarios FORCE ROW LEVEL SECURITY;
ALTER TABLE autonomous_recommendations FORCE ROW LEVEL SECURITY;

-- سياسات عزل المستأجِر الصريحة (تطابق _sahool_apply_tenant_rls في v9):
-- USING فشل-مغلق عند سياق فارغ؛ WITH CHECK يمنع الكتابة عابرة المستأجِر.
DROP POLICY IF EXISTS gis_collaboration_sessions_tenant_isolation ON gis_collaboration_sessions;
CREATE POLICY gis_collaboration_sessions_tenant_isolation ON gis_collaboration_sessions
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );
DROP POLICY IF EXISTS gis_collaboration_events_tenant_isolation ON gis_collaboration_events;
CREATE POLICY gis_collaboration_events_tenant_isolation ON gis_collaboration_events
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );
DROP POLICY IF EXISTS ogc_conformance_runs_tenant_isolation ON ogc_conformance_runs;
CREATE POLICY ogc_conformance_runs_tenant_isolation ON ogc_conformance_runs
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );
DROP POLICY IF EXISTS distributed_raster_jobs_tenant_isolation ON distributed_raster_jobs;
CREATE POLICY distributed_raster_jobs_tenant_isolation ON distributed_raster_jobs
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );
DROP POLICY IF EXISTS digital_twin_scenarios_tenant_isolation ON digital_twin_scenarios;
CREATE POLICY digital_twin_scenarios_tenant_isolation ON digital_twin_scenarios
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );
DROP POLICY IF EXISTS autonomous_recommendations_tenant_isolation ON autonomous_recommendations;
CREATE POLICY autonomous_recommendations_tenant_isolation ON autonomous_recommendations
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );
