# ADR-0033 — Tenant binding for field-management-service `/internal/fields`

- **Status:** Proposed / **Deferred** (design frozen; implementation gated on a trigger — see §6). No code change accompanies this ADR.
- **Date:** 2026-07-18
- **Scope:** `services/field-management-service` `/internal/fields/{id}` and every internal caller of it.
- **Supersedes/relates:** #201 (extraction of internal field-read routes into field-management-service). This ADR does not change #201's runtime today; it records the target that a future change should converge on.
- **Gap:** `FIELD-SVC-TENANT-HEADER-TRUST` (sahool-brain/gaps/registry.md).

## 1. Current model (what exists today)

`/internal/fields/{id}` is **service-token-only**: `_require_service_token` (`main.py:55-70`) verifies `X-Agent-Token` via `hmac.compare_digest` and rejects a bare JWT (401). It does **not** read or verify a user JWT. The tenant is taken **exclusively from a caller-supplied `X-Tenant-Id` header** (`_require_tenant`, `main.py:76-85`); RLS is then enforced with that value (`set_config('app.current_tenant', …)` + `WHERE tenant_id = $2`).

Consequence: **any service holding `SAHOOL_AGENT_TOKEN` can read any tenant's fields** by sending an arbitrary `X-Tenant-Id`. The tenant binding rests on a forgeable header, trusted because the token holder is trusted to derive it honestly from the end-user's JWT.

## 2. Why this is an acceptable risk *temporarily* (not a new regression)

- This is the **documented #201 contract**, not a session regression. The trust simply moved from "a JWT claim can't be forged" to "the calling service derives `X-Tenant-Id` faithfully from the user's JWT."
- The perimeter is authenticated: `SAHOOL_AGENT_TOKEN` is a required, non-empty, secret-manager-backed shared secret; only in-mesh services hold it. RLS is still enforced — it isolates by the *supplied* value, so a bug/compromise is bounded to callers that already hold the agent token.
- The blast radius is "a compromised or buggy **in-mesh service**," not "any external client." That is a materially smaller surface than an unauthenticated endpoint.

The residual risk that this ADR targets: a single leaked/over-broad agent token, or one careless caller, silently reads across tenants with no cryptographic tenant scoping.

## 3. Target design (what we converge on)

Replace the free `X-Tenant-Id` header with a **signed, tenant-scoped claim** that field-management-service verifies and derives the tenant *from* — so the binding is unforgeable even between agent-token holders.

- **Option A (preferred — least leak-prone):** the caller mints a **short-lived service token** carrying a `tid` (tenant-id) claim, signed with the **calling service's key** (or a dedicated internal-mesh signing key, isolated per ADR-0033 the same way ledger #3 isolates the activation keys). field-management-service verifies the signature + expiry and reads `tid` from the verified claim. The end-user JWT never leaves the calling service. Narrow audience (`aud=field-management`), short TTL (seconds–minutes), and `tid` bound at mint time.
- **Option B (simpler — more exposure):** the caller forwards the **full end-user JWT**, and field-management-service verifies it and reads `tid` from the JWT claim. Correct, but spreads the user credential to another service and widens the JWT's reach across the mesh.

**Decision: Option A** when implemented — it keeps the user credential contained and gives field-management a verifiable, minimally-scoped assertion. Option B is the fallback only if a per-caller signing key proves impractical.

## 4. Phased migration (no flag-day)

1. **Accept both:** field-management-service accepts *either* the legacy `X-Tenant-Id` header *or* the signed `tid` claim; when both are present they must agree (else 403). Callers migrate to sending the claim. Backward-compatible.
2. **Warn:** when only the legacy header is present (no claim), emit a loud structured warning (per caller) — surfaces stragglers without breaking them.
3. **Reject header:** once all callers send the claim (warnings quiet), drop `X-Tenant-Id` acceptance; the signed claim becomes the sole tenant source. Header-only requests → 401/403.

Each phase is a normal Ratchet slice with its own tests + a static guard asserting the current phase's contract.

## 5. Consequences

- **Positive:** tenant binding becomes unforgeable even for agent-token holders; a leaked agent token no longer implies cross-tenant read. Aligns the internal channel with the platform's fail-closed, cryptographically-bound posture.
- **Cost:** a signing/verification path in every caller + field-management; key management for the internal-mesh signing key (isolated, per the ledger #3 discipline); three migration slices.
- **Non-goal:** this ADR does **not** change RLS (which stays enforced) — it hardens *how the tenant value is obtained* before RLS runs.

## 6. Implementation trigger

Do **not** implement proactively (main is stable; no incident pressure; security slices land with their tests in normal work windows, not as isolated initiatives). Convert this ADR to code when **either**:

- the **first substantive change to `field-management-service`** lands (fold the migration Phase 1 into that slice), **or**
- a **new consumer of `/internal/fields`** is added (require it to send the signed claim from day one; do not add another header-trusting caller).

When the trigger fires, implementation is a faithful translation of §3–§4, not a re-discovery — and it follows the standard slice path (branch → tests + static guard → CI green → FF).
