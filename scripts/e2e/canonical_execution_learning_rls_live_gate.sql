\set ON_ERROR_STOP on

-- Live RLS qualification for decision-learning runtime tables.
-- Preconditions: v227 applied; sahool_app exists and has INSERT/SELECT privileges.

BEGIN;

DO $$
DECLARE
  t text;
  r record;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sahool_app') THEN
    RAISE EXCEPTION 'sahool_app role missing';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sahool_app' AND (rolsuper OR rolbypassrls)) THEN
    RAISE EXCEPTION 'sahool_app must be NOSUPERUSER and NOBYPASSRLS';
  END IF;
  FOREACH t IN ARRAY ARRAY['decision_learning_runs','governed_model_promotion_candidates'] LOOP
    SELECT c.relrowsecurity, c.relforcerowsecurity INTO r
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='public' AND c.relname=t;
    IF NOT FOUND THEN RAISE EXCEPTION '% table missing', t; END IF;
    IF NOT r.relrowsecurity OR NOT r.relforcerowsecurity THEN
      RAISE EXCEPTION '% must have ENABLE+FORCE RLS', t;
    END IF;
  END LOOP;
END $$;

SET LOCAL ROLE sahool_app;
SELECT set_config('app.current_tenant','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',true);

INSERT INTO decision_learning_runs(
  id,tenant_id,season_id,field_id,event_id,status,outcome_count,
  source_digests,evaluation,learning_digest
) VALUES (
  '11111111-1111-4111-8111-111111111111'::uuid,
  'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'::uuid,
  'cert-season-a','cert-field-a','cert-event-a','blocked',0,
  '[]'::jsonb,'{"fixture":true}'::jsonb,
  repeat('a',64)
) ON CONFLICT (tenant_id,event_id) DO NOTHING;

DO $$
BEGIN
  IF (SELECT count(*) FROM decision_learning_runs WHERE event_id='cert-event-a') <> 1 THEN
    RAISE EXCEPTION 'tenant A cannot read its own decision-learning row';
  END IF;
END $$;

SELECT set_config('app.current_tenant','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',true);

DO $$
BEGIN
  IF (SELECT count(*) FROM decision_learning_runs WHERE event_id='cert-event-a') <> 0 THEN
    RAISE EXCEPTION 'tenant B can read tenant A decision-learning row';
  END IF;
  BEGIN
    INSERT INTO decision_learning_runs(
      tenant_id,season_id,field_id,event_id,status,outcome_count,
      source_digests,evaluation,learning_digest
    ) VALUES (
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'::uuid,
      'cert-season-x','cert-field-x','cert-event-cross','blocked',0,
      '[]'::jsonb,'{}'::jsonb,repeat('b',64)
    );
    RAISE EXCEPTION 'cross-tenant insert unexpectedly accepted';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
END $$;

ROLLBACK;
\echo 'PASS canonical_execution_learning_rls_live_gate'
