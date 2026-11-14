# SAHOOL — Administrative Authorization Remediation · 13 November 2026

Base: main@967f12efc6172606e5c81fe7be169495d87db606.

Scope: tenant-scoped team APIs, atomic invitations, security denial visibility, field task capability, finance writes, DLQ requeue, and frontend tenant-provision response.

1. Team operations recheck signed identity against active DB membership and scope all reads/writes to that tenant; privileged owner/admin targets cannot be modified through team endpoints.
2. Redis session invalidation occurs before DB writes and denies on invalidation failure. An unsuccessful DB write may invalidate a session without changing the account.
3. Invitation acceptance uses one row-locked transaction and conditional consume.
4. Denial HTTP reads return current-tenant events only. Events without tenant attribution are never returned to tenant users.
5. FINANCE_MANAGE restricts budget and revenue writes to owner/manager; ACTIVITY_EXECUTE authorizes task completion for workers; EVENT_REQUEUE separates mutating dead-letter operations from AUDIT_VIEW.
6. Tenant provisioning UI reads owner_email/owner_role/setup_link matching the service response.

Residual risks: the legacy 'admin' alias in the platform still maps to tenant owner; persistent per-farm ACL is absent; denial log is volatile (only HTTP scope fixed); audit persistence remains best effort; and Redis+DB cannot be atomically committed across systems. No production deployment occurred.

Release blockers: full CI and generated inventory regeneration as required; real PostgreSQL and Redis failure tests; simultaneous invite acceptance, two-tenant HTTP role matrix, web/mobile E2E.
