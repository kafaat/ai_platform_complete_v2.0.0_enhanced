-- v128 (v29.5 line) — MFA production hardening.
-- Retro-hardens the v21 MFA (plaintext users.mfa_secret, no recovery/lockout/audit):
--   • encrypted_mfa_secret  — Fernet ciphertext (v1: prefixed); plaintext mfa_secret kept
--     during a transitional window (backfilled on next successful verify, dropped later).
--   • DB-persisted lockout (mfa_failed_attempts / mfa_locked_until) — survives restarts,
--     unlike a process/Prometheus counter.
--   • mfa_recovery_codes — one-time codes, SHA-256 hash only (never plaintext).
--   • mfa_audit_events — forensic trail (enable/disable/verify/lock/recovery).
-- Additive + idempotent. Applied after v127. Auth/identity tables are cross-tenant (the auth
-- service writes them before a tenant context exists) — so RLS mirrors the audit_log pattern
-- (v87): a tenant-scoped policy WITH a service-context escape (unset tenant OR the auth pool's
-- app.current_role='admin'), which keeps login working while still isolating tenant reads.

-- ── users: encryption-at-rest + lockout + lifecycle timestamps ──────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS encrypted_mfa_secret  TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_failed_attempts   INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_locked_until      TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enabled_at        TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_last_verified_at  TIMESTAMPTZ;

COMMENT ON COLUMN users.encrypted_mfa_secret IS
    'سرّ TOTP مشفّر (Fernet، بادئة v1:). يحلّ محلّ mfa_secret النصّيّ تدريجيّاً — حسّاس.';
COMMENT ON COLUMN users.mfa_failed_attempts IS 'عدّاد فشل MFA المتتالي (يُصفَّر عند النجاح).';
COMMENT ON COLUMN users.mfa_locked_until IS 'قفل MFA حتى هذا الوقت بعد تجاوز حدّ الفشل (دائم في DB).';

CREATE INDEX IF NOT EXISTS idx_users_mfa_locked_until
    ON users (mfa_locked_until) WHERE mfa_locked_until IS NOT NULL;

-- ── recovery codes (hash only, one-time) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS mfa_recovery_codes (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id   UUID,                       -- forensic only (nullable); no RLS on auth tables
    code_hash   TEXT        NOT NULL,       -- SHA-256 of the normalized code; never plaintext
    used_at     TIMESTAMPTZ,               -- NULL ⇒ unused; set atomically on consumption
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mfa_recovery_codes_user_used
    ON mfa_recovery_codes (user_id, used_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mfa_recovery_codes_user_hash
    ON mfa_recovery_codes (user_id, code_hash);

-- ── MFA audit events (append-only forensic trail) ───────────────────────────
CREATE TABLE IF NOT EXISTS mfa_audit_events (
    id              BIGSERIAL   PRIMARY KEY,
    user_id         INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    actor_user_id   INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    tenant_id       UUID,
    event           TEXT        NOT NULL,   -- mfa_enabled/mfa_disabled/mfa_verify_failed/...
    outcome         TEXT,                   -- success/failed/locked/…
    ip_hash         TEXT,                   -- hashed IP (no raw PII)
    request_id      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mfa_audit_events_user_created
    ON mfa_audit_events (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_mfa_audit_events_event_created
    ON mfa_audit_events (event, created_at);

-- ── RLS (mirror audit_log/v87): tenant-scoped read + service-context escape ──
-- The auth pool writes these before a tenant context exists (unset app.current_tenant) and
-- with app.current_role='admin' (service-only escape; no human platform user has role 'admin'
-- after the RBAC rework). FORCE subjects the table owner too (defence in depth).
ALTER TABLE mfa_recovery_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE mfa_recovery_codes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mfa_recovery_codes_policy ON mfa_recovery_codes;
CREATE POLICY mfa_recovery_codes_policy ON mfa_recovery_codes
    USING (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
        OR user_id::TEXT = NULLIF(current_setting('app.current_user_id', true), '')
        OR current_setting('app.current_role', true) = 'admin'
    )
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

ALTER TABLE mfa_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE mfa_audit_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mfa_audit_events_policy ON mfa_audit_events;
CREATE POLICY mfa_audit_events_policy ON mfa_audit_events
    USING (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
        OR user_id::TEXT = NULLIF(current_setting('app.current_user_id', true), '')
        OR current_setting('app.current_role', true) = 'admin'
    )
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );
