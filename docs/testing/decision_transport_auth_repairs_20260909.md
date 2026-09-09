# Decision transport and workspace authority repairs — 2026-09-09

Research follow-up: A02 in the agricultural applications/practices comparison.
Repository base: `7407eae2ba006a4c4c07018988a0f680e176abea`.
Previous repair handoff: `7d6102f5f74d5bb7dcc5d16379bf717667e0b911`.
Code repair: `b15871f9c` on `fix/main-irrigation-guardrails-20260909`.

## Corrected behavior

| Caller | Boundary | Credential and authority |
| --- | --- | --- |
| Platform decision facade | decision-service HTTP | Shared decision Bearer; tenant and actor remain those resolved by the platform API. Caller JWT and general agent secret are not substituted. |
| Water-ledger worker | Same platform facade | Startup verifies the same decision credential when identity is required and the bridge is enabled. Disabled bridges and unconfigured development mirrors retain their existing modes. |
| Reservation relay | Same platform facade | Compose injects the receiver's configured secret under the caller variable. No new dispatch or execution path. |
| Vegetation evidence and diagnosis referral | decision-service HTTP | The common credential helper supplies service auth. Missing required credentials prevent an evidence push and return a named reason. Referrals remain pending approval. |
| Remote-sensing workspace BFF | Platform session API, then decision-service reads | Session validation precedes domain requests. Tenant must match the verified session, and recommendation:view must be present in the platform's canonical permission projection. The user JWT goes to user-facing APIs; only decision requests receive the decision secret. |
| Vegetation outcome verification / learning attribution | Existing platform RBAC endpoints | The platform checks DECISION_EXECUTE / DECISION_LEARNING_ATTRIBUTE and derives the actor from the authenticated user. Caller-supplied reviewer/attributor headers are not forwarded as trusted identity. |
| Raster activation reader | Existing decision-service activation endpoint | Compose now injects the DECISION_SERVICE_TOKEN already read by its client. Activation behavior remains opt-in. |

The credential helper lives in `shared/security/decision_service_auth.py`; the platform facade remains `api/decision_service_client.py`. The session permission list uses the existing `core.authorization.has_permission` policy. This repair adds no second permission map, decision store, or device execution route.

## Configuration and rollout

Configure `DECISION_SERVICE_AUTH_TOKEN` at the deployment boundary. Compose maps it to `DECISION_SERVICE_TOKEN` in HTTP callers. For processes launched outside compose, export the caller variable explicitly. Do not place either secret in a browser/mobile configuration.

Deploy the platform session response before the updated workspace BFF: the BFF requires the explicit permission projection and fails closed if an older platform omits it. Preserve each service's existing JWT issuer/key configuration. Service URL/auth configuration does not prove connectivity or database readiness.

Development without required auth remains compatible with the receiver's unconfigured mirror mode. Production or DECISION_REQUIRE_AUTH_TOKEN requires the decision credential. Water-ledger's existing explicit identity flag also requires it. No feature or SoR flag is enabled by this patch.

## Validation evidence

- Before the repair, targeted behavioral witnesses reproduced **5 failures / 12 passes**: wrong credential type, missing production credential and unauthenticated evidence push.
- The focused suite then passed **60 tests**. One intermediate run had 12 test-fixture errors because UserSchema is a dataclass, not a Pydantic model; the fixture now uses dataclasses.replace. No production policy was relaxed to satisfy it.
- Receiver middleware tests passed **10 tests**, including correct and incorrect client credentials against the real decision-service guard.
- The CI vegetation/advisory group, extended to include workspace and outcome bridge regressions, passed **61 tests** in its actual CI working directory.
- Repository-wide Ruff checks and formatting passed. Final generation/preflight results are recorded in the delivery evidence after completion.

HTTP guards and production functions ran with controlled transports and data; this is not a live PostgreSQL/NATS/device certification. Permission/tenant rejection was tested before domain calls. The receiver probe reaches routing after authentication; it does not establish tenant RLS or decision persistence.

## Remaining architecture work

The previous irrigation/evidence/fertilizer repair commits are preserved. This slice addresses the A02 transport mismatch and the related caller-authority defect. A01 SoR promotion, A03 database writer isolation, A04 field-state consolidation, A05 measured execution outcomes, A06 weather event production, A07 knowledge parity, A08 broader MCP data classification, A10 scouting backend integration, A11 per-service NATS permissions and A12 inventory accuracy remain separate, evidence-dependent work. Existing frozen-path and activation decisions remain binding. Runtime verification and production certification are not claimed.
