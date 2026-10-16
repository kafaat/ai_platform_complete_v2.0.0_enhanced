# TTS / platform compatible release plan — 2026-10-16

This is an operation plan, not a deployment receipt. The gap remains open until
runtime conditions are met. The owner delegated the scoped choices; the initial
mode is declared local unavailability with no new external speech grants.

## Measured before-state

Fresh staging observation: 2026-10-16 16:10 UTC, project
`33c50993-1110-43eb-8e92-04c15edae51e`, environment
`70cc51f8-b11f-4506-87b2-4b6615e472be`.

| Service | Active deployment | Source SHA |
| --- | --- | --- |
| platform | `611c4fb7-aba7-4f82-bc7f-fffbb0ed5768` | `df16cc05c4b666397956bd8c721949045e59b680` |
| TTS | `2705c13b-c1bc-4d92-9e19-9331a963f6bb` | `0eaa1e4e2e1deee237ef7238bcd88ea07919a0e4` |

Platform branch: `deploy/sahool-platform-db-ready-eb6da9df`. TTS branch:
`claude/project-exploration-dtjw3p`. TTS has a `PLATFORM_API_URL` variable name;
its redacted value does **not** prove a trusted origin or reachability. No domains
are exposed in these service receipts. Production before-state must be refreshed
separately; staging identifiers are not production identifiers.

Unlike older observations, staging platform already emits an envelope, but the
actual deployed core source emits the legacy contract without contract identity,
contract version, or separate speech grant. Deployed staging TTS consumes the
legacy LLM permission. Therefore successful staging requests on this pair would
not prove the v2 speech privacy contract.

## Candidate source and deployment boundary

The measured baseline candidate is `6e8cc0f9952c037550ae1644919f88c475dd89a7`.
The final integration commit must add the exact contract-identity check and
policy-aware status fields, pass all gates, and replace this baseline in the
release record before deployment. Do not deploy a moving branch or infer an image
SHA from a source SHA; capture both from the build receipt.

`deployed-diff-manifest.json` names every path changed against the actual staging
sources and hashes the full diff retained in the continuation workspace. Platform
plus shared and migration surfaces differ in **87 files** (6386 insertions,
590 deletions). TTS plus shared differs in **12 files** (1055 insertions,
90 deletions). This is not a two-file deployment. In particular, a full platform
promotion activates the U07 writer and requires independently accepted v234
schema first. Platform source also changes irrigation, weather, outcome, RAG,
authentication and shared access-token handling. The inventory does not substitute
for review of those changes.

A narrow platform backport can use only the already merged
`services/sahool-platform/core/ai_policy_envelope.py` and
`services/sahool-platform/api/routers/me.py` onto the observed deployed parent:
the contract is additive and uses existing `allowed_providers` data, with no new
column. Such a release would need its own exact tree, tests and approved deployment
record; it has not been created or deployed by this work. The unified PR remains
the source delivery for this task.

## Ordered operation

1. Refresh active deployment IDs and source/image SHAs in both environments.
   Stop and review any change against the identifiers above. Preserve their
   configuration snapshot; do not copy secret values into evidence.
2. Choose the final compatible source pair only after the relevant schema and
   authentication prerequisites have passed. A full platform promotion must not
   precede the U07 schema acceptance. No migration/global apply flag is changed
   by this plan.
3. Observe the platform private hostname and actual listener port through Railway
   service networking/configuration. Build `PLATFORM_API_URL` from that verified
   origin only. Validate host, port, private route and `/api/v1/me` authentication;
   no guessed hostname, redirect, credentials in URL, or external proxy.
4. With named synthetic identity, verify platform v2 envelope tenant matches the
   verified token and speech permission is denied. Do not add `tts:*` entries or
   modify existing tenant sharing policy. Deploy the selected TTS image and
   configure only its trusted platform origin as needed. No provider model or
   external account is provisioned: missing local provider is the declared mode.
5. Use existing authenticated `/v1/tts/status`: `policy_eligible_provider=null`,
   `policy_mode=local_only`, and
   `unavailable_reason=local_provider_unavailable_for_policy`. Raw provider
   inventory may show Edge installed; this does not authorize its use. Status
   is an eligibility snapshot, not proof that synthesis succeeded.
6. Exercise synthesis and streaming with synthetic content while observing the
   runtime egress boundary. Require the named 503 before streaming starts, zero
   forbidden attempts/requests for denied and malformed envelopes, tenant
   mismatch, missing origin, platform error, LLM-only permission and absent named
   provider. Retain source/image identity and aggregate counts only. The local
   26-case CPython socket proof is supporting evidence, not this runtime receipt.
7. Promote the same tested compatible pair to production only after staging
   evidence is complete and the concrete production scope is accepted. Verify
   production source/image hashes, origin and the same denial behavior.

## Recovery

Retain the previous deployment/configuration identifiers for provenance, but do
not restore the legacy staging TTS policy consumer: it couples LLM permission to
speech permission. If the v2 platform is unavailable, keep v2 TTS fail-closed and
declare local speech unavailable. Restore only a previously tested compatible v2
pair, or pause speech while correcting forward. Do not restore external fallback
or delete accepted U07 schema/values to recover speech availability.

## Executed source acceptance

See `acceptance-summary.json`: five contract identity witnesses and two status
witnesses fail on the baseline; four real Edge socket cases fail on the baseline.
The fixed policy/provider suite passes 149 tests. The native local network matrix
passes 26 cases, including 24 denied cases without a forbidden socket attempt and
two valid-grant positive controls that reach and are stopped by the boundary.
No provider method or policy-fetch function is mocked in that matrix. Its CPython
audit instrumentation does not claim kernel-wide observation of native code.
No Railway changes or external speech requests were performed by the TTS agent.
