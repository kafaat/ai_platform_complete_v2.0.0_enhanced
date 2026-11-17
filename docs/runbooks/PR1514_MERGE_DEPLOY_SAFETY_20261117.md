# #1514 — Merge and Railway safety gates (17 November 2026)

> **Updated post-merge readback (2026-11-17).** #1514 was squash-merged to
> `main@6fc43793da413da909b362892bfefdc6e4a5ef25` at 13:16:05 UTC.
> The four `main`-watched Railway service builds were triggered: frontend
> production/staging and decision-service production succeeded; decision-service
> staging build failed at BUILD_IMAGE with no captured build logs. Its previously
> successful deployment remained online at the time of the readback. This is an
> incident/status record, not an owner authorization for a redeploy or a claim
> that the failed revision is running in staging.
>
> **#1516 is now the separately reviewed follow-up on merged `main`.** Its
> physical-execution result and UI contract must pass their own CI and, if
> required, composite laboratory receipt on the eventual #1516 head. No re-merge
> of #1514, no change to Railway service sources, and no auto-deployment bypass.

**Target composite:** `kafaat/ai_platform_complete_v2.0.0_enhanced#1514`, head
`9d698e1b14a311a817b94cf6bf34d81754e1ba46`. Source PRs:
#1511 (`8dd0b338`), #1512 (`39db514d`), #1513 (`6f3b819a`),
closed unmerged and incorporated in the composite. This note records a **hold**,
not an authorization or evidence that a Railway build has deployed.

## Merge policy

- The active `main` branch rule requires **linear history**. Do not use a
  multi-parent Merge Commit. Prefer **Squash and Merge** (when allowed by
  branch protection) with all four source/composite SHAs retained in the squash
  commit message and PR description for provenance.
- Verify the required checks on the *final* composite SHA; Codecov/patch
  success is measured separately from the list of required branch checks.
  A superseded failed run is not an active failure if the retry passed.
- Independent reviewer `haithmgarallah-ye` remains requested; GitHub does
  not let `kafaat` approve a PR it authored. A `COMMENTED` review is not
  `APPROVED`. Obtain the independent review in the team's process.
- Establish whether an independent unified-local-lab PASS receipt is a
  hard requirement for the **same composite SHA**. Do not substitute
  receipts for #1511/#1512/#1513; an unexecuted chaos test is not certified.
- Before merging, obtain the **owner's prior explicit approval** for the four
  *potential automatic Railway rebuilds*, or apply a separately authorized
  deployment-trigger hold and prove it before merging.

## Railway scope verified 2026-11-17

| Service | Environment | Source | Watches (relevant) |
|---|---|---|---|
| `sahool-frontend` | production | `main` | `/frontend/**` |
| `sahool-frontend` | staging | `main` | `/frontend/**` |
| `sahool-decision-service` | production | `main` | `/services/decision-service/**` |
| `sahool-decision-service` | staging | `main` | `/services/decision-service/**` |
| `sahool-platform` | production | `deploy/sahool-staging-fa92a1f7` | separate branch |
| `sahool-platform` | staging | `deploy/sahool-platform-db-ready-eb6da9df` | separate branch |

`#1514` changes both watched path families; its merge is **not** a
deployment-neutral operation. No Railway source change, staging patch,
deployment, or restart is permitted by this document. Platform fixes need
a separately reviewed promotion to their two deployment branches.

## Agricultural execution truth

`POST /api/v1/pest-escalation/run` distinguishes workflow progress
(`workflow.status`) from agricultural action (`execution.status`).
`execution.status = executed` requires literal `executed: true` and a real
nonempty `execution_ref` on a completed workflow. A completed workflow
without an executor is `not_executed`; unresolved partial execution,
a failed saga after an execution, or failed compensation returns
`reconciliation_required` with `executed: null`.
Existing `step_results.execute` remains unchanged for older web/mobile clients.
The new web and mobile screens consume `execution` first when present; their
legacy fallback is retained for servers which have not yet been upgraded.
Reconciliation is presented as **uncertain**, never as a confirmed negative.

The HTTP router currently supplies **no** `execute_fn`: the physical spray
integration remains a separately tracked gap. Never imply a spray occurred
from a workflow `COMPLETED` state.

## Evidence scope

Source: #1514 core CI 44051090737, governance retry 44053830212,
production gates 44051090495; GitHub checks and the Railway service
configurations reviewed on 17 November 2026. These do not authorize merging
or deploying.
