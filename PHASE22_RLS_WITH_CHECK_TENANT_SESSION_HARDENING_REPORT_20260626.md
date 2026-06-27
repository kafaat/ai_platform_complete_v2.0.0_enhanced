# Phase 22 — RLS WITH CHECK + Tenant Session Hardening

## Purpose

This phase closes the remaining high-priority tenant isolation gap found during the deep source audit:
legacy and active migrations contained tenant RLS write policies defined with `USING` only and no `WITH CHECK`.
That pattern filters reads but does not validate inserted or updated tenant-owned rows.

## Implemented Changes

- Added `migrations/v122_rls_with_check_session_unification.sql`.
- Added `public.sahool_effective_tenant_id()` to normalize tenant context:
  - canonical: `app.current_tenant`
  - compatibility: `app.tenant_id`
- Added a catalog-driven backfill that alters tenant-aware `ALL`/`INSERT`/`UPDATE` policies missing `WITH CHECK`.
- Preserved nullable `tenant_id` system-row semantics where existing tables allowed `tenant_id IS NULL`.
- Added a post-backfill assertion that raises if any tenant write policy remains without `WITH CHECK`.
- Updated Phase runtime store/workers to set both `app.current_tenant` and `app.tenant_id` transaction-locally.
- Added `scripts/security/validate_rls_write_policies.py` and integrated it into production and CI gates.
- Added regression tests in `tests/security/test_phase22_rls_with_check_backfill.py`.

## Status

This phase does not claim field certification. It closes the verified RLS write-path class and adds gates to prevent new migrations from reintroducing tenant write policies without `WITH CHECK`.
