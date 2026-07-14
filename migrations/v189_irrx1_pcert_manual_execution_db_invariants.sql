-- IRR-PCERT: database-authoritative invariants for the governed manual irrigation path.
-- The application state machine remains useful for clear API errors, but PostgreSQL is
-- the final authority: direct SQL cannot skip approval/verification/reconciliation or
-- rewrite evidence after a legal transition.

CREATE OR REPLACE FUNCTION sahool_irrx1_manual_execution_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    allowed boolean := false;
BEGIN
    -- Legal identity and recommendation inputs are immutable after creation.
    IF (NEW.tenant_id, NEW.field_id, NEW.season_id, NEW.system_id,
        NEW.recommendation_id, NEW.recommendation_digest, NEW.execution_mode,
        NEW.target_depth_mm, NEW.target_volume_m3, NEW.nominal_flow_m3_h,
        NEW.valid_from, NEW.valid_until, NEW.idempotency_key, NEW.created_by,
        NEW.created_at)
       IS DISTINCT FROM
       (OLD.tenant_id, OLD.field_id, OLD.season_id, OLD.system_id,
        OLD.recommendation_id, OLD.recommendation_digest, OLD.execution_mode,
        OLD.target_depth_mm, OLD.target_volume_m3, OLD.nominal_flow_m3_h,
        OLD.valid_from, OLD.valid_until, OLD.idempotency_key, OLD.created_by,
        OLD.created_at) THEN
        RAISE EXCEPTION 'IRRX1_IMMUTABLE_EXECUTION_IDENTITY';
    END IF;

    IF NEW.state = OLD.state THEN
        -- Idempotent reads/upserts may touch updated_at only. Legal evidence is never
        -- editable in-place while the state is unchanged.
        IF (NEW.approved_at, NEW.started_at, NEW.stopped_at, NEW.confirmed_at,
            NEW.verified_at, NEW.reconciled_at, NEW.completion_ratio,
            NEW.confirmation, NEW.as_applied, NEW.as_applied_digest,
            NEW.ledger_eligible, NEW.verification, NEW.verification_digest,
            NEW.verified_by, NEW.ledger_event_digest)
           IS DISTINCT FROM
           (OLD.approved_at, OLD.started_at, OLD.stopped_at, OLD.confirmed_at,
            OLD.verified_at, OLD.reconciled_at, OLD.completion_ratio,
            OLD.confirmation, OLD.as_applied, OLD.as_applied_digest,
            OLD.ledger_eligible, OLD.verification, OLD.verification_digest,
            OLD.verified_by, OLD.ledger_event_digest) THEN
            RAISE EXCEPTION 'IRRX1_EVIDENCE_REWRITE_REQUIRES_LEGAL_TRANSITION';
        END IF;
        RETURN NEW;
    END IF;

    allowed := CASE OLD.state
        WHEN 'recommended' THEN NEW.state IN ('approved', 'cancelled')
        WHEN 'approved'    THEN NEW.state IN ('started', 'cancelled')
        WHEN 'started'     THEN NEW.state = 'stopped'
        WHEN 'stopped'     THEN NEW.state IN ('confirmed', 'cancelled')
        WHEN 'confirmed'   THEN NEW.state = 'verified'
        WHEN 'verified'    THEN NEW.state = 'reconciled'
        ELSE false
    END;
    IF NOT allowed THEN
        RAISE EXCEPTION 'IRRX1_INVALID_DB_TRANSITION:%->%', OLD.state, NEW.state;
    END IF;

    IF NEW.state = 'approved' AND NEW.approved_at IS NULL THEN
        RAISE EXCEPTION 'IRRX1_APPROVAL_TIMESTAMP_REQUIRED';
    ELSIF NEW.state = 'started' AND NEW.started_at IS NULL THEN
        RAISE EXCEPTION 'IRRX1_START_TIMESTAMP_REQUIRED';
    ELSIF NEW.state = 'stopped' AND NEW.stopped_at IS NULL THEN
        RAISE EXCEPTION 'IRRX1_STOP_TIMESTAMP_REQUIRED';
    ELSIF NEW.state = 'confirmed' THEN
        IF NEW.confirmed_at IS NULL OR NEW.confirmation IS NULL OR NEW.as_applied IS NULL
           OR NEW.as_applied_digest IS NULL OR NEW.completion_ratio IS NULL THEN
            RAISE EXCEPTION 'IRRX1_CONFIRMATION_EVIDENCE_REQUIRED';
        END IF;
    ELSIF NEW.state = 'verified' THEN
        IF NEW.verified_at IS NULL OR NEW.verified_by IS NULL OR NEW.verification IS NULL
           OR NEW.verification_digest IS NULL OR NEW.as_applied_digest IS NULL
           OR NOT NEW.ledger_eligible THEN
            RAISE EXCEPTION 'IRRX1_VERIFICATION_EVIDENCE_REQUIRED';
        END IF;
        IF NEW.as_applied_digest IS DISTINCT FROM OLD.as_applied_digest
           OR NEW.as_applied IS DISTINCT FROM OLD.as_applied
           OR NEW.confirmation IS DISTINCT FROM OLD.confirmation THEN
            RAISE EXCEPTION 'IRRX1_CONFIRMED_TRUTH_IS_IMMUTABLE';
        END IF;
    ELSIF NEW.state = 'reconciled' THEN
        IF NEW.reconciled_at IS NULL OR NEW.ledger_event_digest IS NULL
           OR OLD.verification_digest IS NULL THEN
            RAISE EXCEPTION 'IRRX1_RECONCILIATION_EVIDENCE_REQUIRED';
        END IF;
        IF NEW.as_applied_digest IS DISTINCT FROM OLD.as_applied_digest
           OR NEW.verification_digest IS DISTINCT FROM OLD.verification_digest
           OR NEW.verification IS DISTINCT FROM OLD.verification THEN
            RAISE EXCEPTION 'IRRX1_VERIFIED_TRUTH_IS_IMMUTABLE';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS irrigation_manual_executions_legal_state_guard
    ON irrigation_manual_executions;
CREATE TRIGGER irrigation_manual_executions_legal_state_guard
BEFORE UPDATE ON irrigation_manual_executions
FOR EACH ROW EXECUTE FUNCTION sahool_irrx1_manual_execution_guard();

-- Tenant-scoped composite keys make child-table ownership explicit, not merely
-- inferred from globally unique UUIDs.
CREATE UNIQUE INDEX IF NOT EXISTS irrigation_manual_executions_tenant_execution_uq
    ON irrigation_manual_executions (tenant_id, execution_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'irrigation_manual_events_tenant_execution_fk'
    ) THEN
        ALTER TABLE irrigation_manual_execution_events
        ADD CONSTRAINT irrigation_manual_events_tenant_execution_fk
        FOREIGN KEY (tenant_id, execution_id)
        REFERENCES irrigation_manual_executions (tenant_id, execution_id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'irrigation_manual_reconciliation_tenant_execution_fk'
    ) THEN
        ALTER TABLE irrigation_manual_ledger_reconciliations
        ADD CONSTRAINT irrigation_manual_reconciliation_tenant_execution_fk
        FOREIGN KEY (tenant_id, execution_id)
        REFERENCES irrigation_manual_executions (tenant_id, execution_id);
    END IF;
END $$;
