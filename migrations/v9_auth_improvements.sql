
-- ════════════════════════════════════════════════════════════
-- SAHOOL v9.1 — audit_log table (للعمليات الأمنية الحساسة)
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL    PRIMARY KEY,
    action      VARCHAR(50)  NOT NULL,
    user_id     INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    ip_address  INET,
    details     TEXT,
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user      ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_action    ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_created   ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_ip        ON audit_log(ip_address);

-- RLS: audit_log يرى كل المستأجرين (للمدير فقط)
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS audit_admin_only ON audit_log;
-- FIX M04: allow admins (role=admin) to see audit log, not just superusers
CREATE POLICY audit_log_policy ON audit_log
    USING (
        current_setting('app.current_tenant', true) = ''   -- service context
        OR user_id::TEXT = NULLIF(current_setting('app.current_user_id', true), '')
        OR current_setting('app.current_role', true) = 'admin'  -- H22 FIX: admin sees all
    );

COMMENT ON TABLE audit_log IS 'سجل العمليات الأمنية: login, logout, password_reset, change_password';
