# PR #1252 — LiveKit readiness security reconciliation (2026-10-23)

This is source and local fixture evidence, not deployment or LiveKit certification.

## Inputs and scope

- PR source head: `95df92a2b591b383702388284adc70e7b3baf50f`.
- Integrated main: `617f03664073b7d22db8d43f53e9af848f6dc999`.
- Full independent worktree; no source conflicts. Generated conflicts are resolved
  by the repository canonical generators, never by hand-edited hashes.
- Preserve camera event serialization and tenant AI policy changes. Correct stale
  comments to match the enforced local and external generation envelope gate.
- Real nginx response testing exposed missing security headers after the SPA
  internal redirect to `/index.html`: that location declares cache `add_header`
  directives and therefore does not inherit server security headers.
- Restore the document security headers there. Keep media capture denied on every
  SPA document. `/realtime` has no implemented route; its BrowserRouter fallback
  and subsequent client navigation do not isolate the document permission grant.

## Validation and continuation

`validation.json` records input identities, runtime fixture results, source hashes,
and the remaining check status. The final source, generator and preflight checks
must pass on the candidate before pushing. GitHub CI must then pass on the new
head against current main. Older CI measured a different synthetic merge and is
not reused as proof of this candidate.

## Outstanding acceptance

- `FRONTEND-SPA-CACHE-HEADERS-DROP-SECURITY-01`: candidate fix, final CI/merge
  pending; inspect final deployed edge headers separately.
- `LIVEKIT-REALTIME-DOCUMENT-ISOLATION-PENDING-01`: open; media remains disabled.
- External event consumers outside this repository are not enumerated by source
  search. Verify the `source_url` to `source_type` contract with their owners.
- Platform/TTS v2 staging receipt and instrumented no-external-egress acceptance
  are separate from local policy tests; neither is certified here.
- No session issuer, SFU/worker deployment, STT/VAD, PCM adapter, mobile/web
  calling UI or TURN acceptance is implemented or deployed by this repair.

First safe action after an interruption: read `validation.json`, inspect the PR
head and current main, reconcile the validity inputs, and resume the first pending
check. Do not repeat an external action without reading its target state.
