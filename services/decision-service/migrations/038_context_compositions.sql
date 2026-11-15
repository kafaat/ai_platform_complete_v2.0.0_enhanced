-- Immutable receipt for the exact references the composer returned, including idempotent reuse.
CREATE TABLE IF NOT EXISTS decision_context_compositions (
    tenant_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    snapshot_id text NOT NULL,
    historical_snapshot_id text NOT NULL,
    feature_manifest_id text NOT NULL,
    request_hash text NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, snapshot_id)
      REFERENCES decision_agronomic_context_snapshots (tenant_id, snapshot_id),
    FOREIGN KEY (tenant_id, historical_snapshot_id)
      REFERENCES decision_field_historical_context_snapshots (tenant_id, historical_snapshot_id),
    FOREIGN KEY (tenant_id, feature_manifest_id)
      REFERENCES decision_feature_manifests (tenant_id, feature_manifest_id)
);
CREATE INDEX IF NOT EXISTS idx_context_composition_refs
  ON decision_context_compositions (tenant_id, snapshot_id, historical_snapshot_id, feature_manifest_id);
ALTER TABLE decision_context_compositions ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_context_compositions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON decision_context_compositions;
CREATE POLICY tenant_isolation ON decision_context_compositions
  USING (tenant_id = nullif(current_setting('app.current_tenant',true),'')::uuid)
  WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant',true),'')::uuid);
DROP TRIGGER IF EXISTS trg_context_composition_immutable ON decision_context_compositions;
CREATE TRIGGER trg_context_composition_immutable BEFORE UPDATE OR DELETE ON decision_context_compositions
  FOR EACH ROW EXECUTE FUNCTION decision_wx11_completion_append_only();

-- Existing deployments grant their runtime role access before later migrations run.
-- The receipt inherits only explicit read/append privileges from its parent snapshots.
DO $$
DECLARE grant_row record;
BEGIN
    FOR grant_row IN
        SELECT roles.rolname AS grantee, acl.privilege_type
        FROM pg_class AS parent
        CROSS JOIN LATERAL aclexplode(parent.relacl) AS acl
        JOIN pg_roles AS roles ON roles.oid = acl.grantee
        WHERE parent.oid = 'decision_agronomic_context_snapshots'::regclass
          AND acl.grantee <> parent.relowner
          AND acl.privilege_type IN ('SELECT', 'INSERT')
    LOOP
        EXECUTE format('GRANT %s ON decision_context_compositions TO %I',
                       grant_row.privilege_type, grant_row.grantee);
    END LOOP;
END $$;
