-- v205: IRR-F01 production-boundary hardening.
BEGIN;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Project-coherent identities for all cross-table references introduced by v195/v196.
CREATE UNIQUE INDEX IF NOT EXISTS uq_hydraulic_node_project_tenant
  ON irrigation_hydraulic_nodes (id, project_id, tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_hydraulic_capability_project_tenant
  ON canonical_hydraulic_capabilities (capability_id, project_id, tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_capacity_evaluation_project_tenant
  ON hydraulic_capacity_evaluations (evaluation_id, project_id, tenant_id);

ALTER TABLE irrigation_resource_reservations
  DROP CONSTRAINT IF EXISTS irrigation_resource_reservations_resource_node_id_tenant_id_fkey,
  DROP CONSTRAINT IF EXISTS irrigation_resource_reservations_evaluation_id_tenant_id_fkey;
ALTER TABLE irrigation_resource_reservations
  ADD CONSTRAINT fk_reservation_node_project
    FOREIGN KEY (resource_node_id, project_id, tenant_id)
    REFERENCES irrigation_hydraulic_nodes(id, project_id, tenant_id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_reservation_evaluation_project
    FOREIGN KEY (evaluation_id, project_id, tenant_id)
    REFERENCES hydraulic_capacity_evaluations(evaluation_id, project_id, tenant_id) ON DELETE RESTRICT;

ALTER TABLE irrigation_target_bindings
  DROP CONSTRAINT IF EXISTS irrigation_target_bindings_terminal_node_id_tenant_id_fkey;
ALTER TABLE irrigation_target_bindings
  ADD CONSTRAINT fk_target_binding_node_project
    FOREIGN KEY (terminal_node_id, project_id, tenant_id)
    REFERENCES irrigation_hydraulic_nodes(id, project_id, tenant_id) ON DELETE RESTRICT;

ALTER TABLE hydraulic_capacity_evaluations
  DROP CONSTRAINT IF EXISTS hydraulic_capacity_evaluations_canonical_hydraulic_capability_id_tenant_id_fkey,
  DROP CONSTRAINT IF EXISTS hydraulic_capacity_evaluations_bottleneck_node_id_tenant_id_fkey;
ALTER TABLE hydraulic_capacity_evaluations
  ADD CONSTRAINT fk_capacity_capability_project
    FOREIGN KEY (canonical_hydraulic_capability_id, project_id, tenant_id)
    REFERENCES canonical_hydraulic_capabilities(capability_id, project_id, tenant_id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_capacity_bottleneck_project
    FOREIGN KEY (bottleneck_node_id, project_id, tenant_id)
    REFERENCES irrigation_hydraulic_nodes(id, project_id, tenant_id) ON DELETE RESTRICT;

-- Defense in depth: direct SQL cannot create overlapping live exclusive reservations.
ALTER TABLE irrigation_resource_reservations
  DROP CONSTRAINT IF EXISTS ex_irrigation_exclusive_reservation_overlap;
ALTER TABLE irrigation_resource_reservations
  ADD CONSTRAINT ex_irrigation_exclusive_reservation_overlap
  EXCLUDE USING gist (
    tenant_id WITH =,
    resource_node_id WITH =,
    active_interval WITH &&
  ) WHERE (resource_policy = 'exclusive' AND state IN ('reserved','active'));

CREATE OR REPLACE FUNCTION reject_capacity_evaluation_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'hydraulic_capacity_evaluations is immutable' USING ERRCODE='55000';
END $$;
DROP TRIGGER IF EXISTS trg_capacity_evaluations_immutable ON hydraulic_capacity_evaluations;
CREATE TRIGGER trg_capacity_evaluations_immutable
BEFORE UPDATE OR DELETE ON hydraulic_capacity_evaluations
FOR EACH ROW EXECUTE FUNCTION reject_capacity_evaluation_mutation();

CREATE OR REPLACE FUNCTION guard_target_binding_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.terminal_node_id IS DISTINCT FROM NEW.terminal_node_id
     OR OLD.target_type IS DISTINCT FROM NEW.target_type
     OR OLD.target_id IS DISTINCT FROM NEW.target_id
     OR OLD.target_version_id IS DISTINCT FROM NEW.target_version_id
     OR OLD.valid_from IS DISTINCT FROM NEW.valid_from THEN
    RAISE EXCEPTION 'target binding identity/history is immutable; close and insert a successor'
      USING ERRCODE='55000';
  END IF;
  IF OLD.valid_to IS NOT NULL AND NEW.valid_to IS DISTINCT FROM OLD.valid_to THEN
    RAISE EXCEPTION 'closed target binding cannot be rewritten' USING ERRCODE='55000';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_target_binding_immutable_identity ON irrigation_target_bindings;
CREATE TRIGGER trg_target_binding_immutable_identity
BEFORE UPDATE ON irrigation_target_bindings
FOR EACH ROW EXECUTE FUNCTION guard_target_binding_mutation();

CREATE OR REPLACE FUNCTION validate_target_binding_terminal()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE nt TEXT;
BEGIN
  SELECT node_type INTO nt FROM irrigation_hydraulic_nodes
   WHERE id=NEW.terminal_node_id AND project_id=NEW.project_id AND tenant_id=NEW.tenant_id;
  IF nt IS NULL OR nt NOT IN ('zone','machine_inlet','valve') THEN
    RAISE EXCEPTION 'terminal node type % is not bindable', COALESCE(nt,'missing') USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_target_binding_terminal_type ON irrigation_target_bindings;
CREATE TRIGGER trg_target_binding_terminal_type
BEFORE INSERT OR UPDATE OF terminal_node_id, project_id, tenant_id ON irrigation_target_bindings
FOR EACH ROW EXECUTE FUNCTION validate_target_binding_terminal();

CREATE OR REPLACE FUNCTION transition_irrigation_reservation(
  p_tenant UUID, p_reservation UUID, p_target_state TEXT,
  p_reason TEXT DEFAULT NULL, p_causation UUID DEFAULT NULL, p_correlation UUID DEFAULT NULL
) RETURNS irrigation_resource_reservations LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE r irrigation_resource_reservations; ev TEXT;
BEGIN
  SELECT * INTO r FROM irrigation_resource_reservations
   WHERE tenant_id=p_tenant AND reservation_id=p_reservation FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'reservation not found' USING ERRCODE='P0002'; END IF;
  IF NOT ((r.state='reserved' AND p_target_state IN ('active','expired','cancelled'))
       OR (r.state='active' AND p_target_state IN ('released','cancelled'))) THEN
    RAISE EXCEPTION 'illegal reservation transition % -> %', r.state, p_target_state USING ERRCODE='23514';
  END IF;
  UPDATE irrigation_resource_reservations SET state=p_target_state,
    activated_at=CASE WHEN p_target_state='active' THEN COALESCE(activated_at,NOW()) ELSE activated_at END,
    released_at=CASE WHEN p_target_state IN ('released','expired','cancelled') THEN NOW() ELSE released_at END,
    release_reason=CASE WHEN p_target_state IN ('released','expired','cancelled') THEN p_reason ELSE release_reason END
   WHERE reservation_id=p_reservation AND tenant_id=p_tenant RETURNING * INTO r;
  ev := CASE p_target_state WHEN 'active' THEN 'activated' ELSE p_target_state END;
  INSERT INTO irrigation_resource_reservation_events(tenant_id,reservation_id,event_type,causation_id,correlation_id,payload)
  VALUES(p_tenant,p_reservation,ev,p_causation,COALESCE(p_correlation,r.correlation_id,gen_random_uuid()),
         jsonb_build_object('from_state',CASE WHEN p_target_state='active' THEN 'reserved' ELSE NULL END,'to_state',p_target_state,'reason',p_reason));
  RETURN r;
END $$;

COMMIT;
