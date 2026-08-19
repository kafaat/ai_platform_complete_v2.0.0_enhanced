-- S5-EXEC-01 / S4 Decision cutover compatibility for recommendation_outcomes.
--
-- Converges the legacy platform table and the decision-service-created table into one
-- additive shape without treating recommendation_id as row identity.  Historical platform
-- semantics allow multiple observations for one recommendation; outcome_id is the row identity
-- and idempotency_key (when supplied) is the replay identity.

ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS outcome_id BIGSERIAL;
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS idempotency_key text;
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS request_hash text;
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS decision_id text;
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS outcome text NOT NULL DEFAULT 'pending';
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS confidence double precision;
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

-- Legacy projection columns remain available while read edges migrate independently.
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS farm_id text;
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS crop text;
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS predicted_yield_t_ha numeric(8,3);
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS actual_yield_t_ha numeric(8,3);
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS accepted boolean NOT NULL DEFAULT false;
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS matured_within_lag boolean NOT NULL DEFAULT false;
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS issued_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE recommendation_outcomes ADD COLUMN IF NOT EXISTS outcome_recorded_at timestamptz;

-- 001_decision_sor used (tenant_id,recommendation_id) as PK on a fresh decision DB. That is
-- not compatible with the platform contract. Drop ONLY that exact PK shape; never drop a
-- legacy outcome_id primary key.
DO $$
DECLARE
  pk_name text;
  pk_cols text[];
BEGIN
  SELECT c.conname,
         array_agg(a.attname ORDER BY u.ord)
    INTO pk_name, pk_cols
  FROM pg_constraint c
  JOIN unnest(c.conkey) WITH ORDINALITY AS u(attnum, ord) ON true
  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = u.attnum
  WHERE c.conrelid = 'recommendation_outcomes'::regclass
    AND c.contype = 'p'
  GROUP BY c.conname;

  IF pk_cols = ARRAY['tenant_id','recommendation_id']::text[] THEN
    EXECUTE format('ALTER TABLE recommendation_outcomes DROP CONSTRAINT %I', pk_name);
  END IF;
END $$;

ALTER TABLE recommendation_outcomes ALTER COLUMN outcome_id SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'recommendation_outcomes'::regclass AND contype = 'p'
  ) THEN
    ALTER TABLE recommendation_outcomes
      ADD CONSTRAINT recommendation_outcomes_pkey PRIMARY KEY (outcome_id);
  END IF;
END $$;

-- Replay identity, not recommendation lineage, is unique. NULL means "no idempotency claim".
CREATE UNIQUE INDEX IF NOT EXISTS ux_recommendation_outcomes_tenant_idempotency
  ON recommendation_outcomes (tenant_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_recommendation_outcomes_tenant_recommendation
  ON recommendation_outcomes (tenant_id, recommendation_id);
