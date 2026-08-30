# GATE-01 independent authority and runtime-image supply-chain runbook

## Purpose and current measured state

This runbook closes the external control plane around the repository controls. It does not
authorize touching the physical-effect frozen paths and does not set
`runtime_verified=true` or `production_certified=true`.

Measured from GitHub on 2026-08-30:

- repository: `kafaat/ai_platform_complete_v2.0.0_enhanced`
- active ruleset: `main-protection` (`20645828`)
- target: default branch (`main`)
- bypass actors: none; `current_user_can_bypass=never`
- conversation resolution: enabled
- required status checks: 15 and aligned with the repository contract
- **blocking gap:** `required_approving_review_count=0`
- **blocking gap:** `require_code_owner_review=false`
- **blocking gap:** `require_last_push_approval=false`

The repository-side guard is already fail-closed: when an adjudication path is changed,
`branch_protection_contract_guard.py` requires live Ruleset evidence showing
`require_code_owner_review=true`. The missing operation is an administrator change in GitHub,
not another in-repository policy engine.

## 1. Establish an independent reviewer

Do not proceed with an account that is also the change requester as the only CODEOWNER.
Create or select one of the following:

1. an organization team with at least one independent security/release owner; or
2. a second named repository collaborator who is not the requester; or
3. a GitHub App whose approval is backed by an external authorization service and whose key is
   outside the workflow/repository trust domain.

Update `.github/CODEOWNERS` to assign the adjudication directory and policy to that independent
identity/team. The current `@kafaat` entry alone does not establish two-person authority when the
same identity requests the change.

## 2. Harden ruleset 20645828

In GitHub: **Settings → Rules → Rulesets → main-protection**. Preserve the current status checks
and all existing rules, then set:

| Setting | Required value |
|---|---:|
| Enforcement | Active |
| Required approving reviews | 1 or more |
| Dismiss stale approvals on new commits | Enabled |
| Require review from Code Owners | Enabled |
| Require approval of the most recent reviewable push | Enabled |
| Require conversation resolution | Enabled |
| Bypass actors | Empty |

Save the ruleset. Do not add a repository administrator, Actions bot, or the requesting identity
as a bypass actor.

Read-only verification, using a GitHub token allowed to read repository rules:

```bash
repo='kafaat/ai_platform_complete_v2.0.0_enhanced'
ruleset_id='20645828'
gh api "repos/${repo}/rulesets/${ruleset_id}" > /tmp/sahool-main-ruleset.json
jq -e '
  .enforcement == "active" and
  (.bypass_actors | length) == 0 and
  ([.rules[] | select(.type == "pull_request")][0].parameters |
    .required_approving_review_count >= 1 and
    .dismiss_stale_reviews_on_push == true and
    .require_code_owner_review == true and
    .require_last_push_approval == true and
    .required_review_thread_resolution == true)
' /tmp/sahool-main-ruleset.json
```

Expected exit code: `0`. Any other result leaves GATE-01 external authority unestablished.

## 3. Validate repository guards before requesting authorization

```bash
python scripts/ci/branch_protection_contract_guard.py \
  --protection-file /path/to/live-rules-envelope.json \
  --expect-repository kafaat/ai_platform_complete_v2.0.0_enhanced \
  --expect-sha "$(git rev-parse HEAD)" \
  --changed-files /path/to/changed-files.txt

python scripts/ci/gate01_frozen_path_guard.py --stdin < /path/to/changed-files.txt
python scripts/ci/guard_mutation_guard.py --run --only gate01_frozen_path_guard.py
```

The protection evidence must be freshly fetched for the same repository, `main`, and tested SHA.
An old JSON file or an HTTP error body is not evidence.

## 4. Issue a scoped GATE-01 authorization

Only the independent owner may approve the adjudication PR. The adjudication must bind:

- the GATE ID and frozen Phase-0 baseline;
- exactly the frozen paths being changed;
- the Git blob SHA of every authorized resulting file;
- the canonical patch SHA-256;
- `status=ISSUED` and one-time semantics;
- the reviewing identity and PR.

After any byte changes, regenerate the binding and obtain a new independent review. Never reuse a
prior authorization. After merge, stamp it `CONSUMED` with the actual merge SHA and date; an
`ISSUED` record whose bytes have landed is a blocking stale authorization.

## 5. Runtime image build, scan, SBOM, and attestation

Dispatch **Runtime Image Provenance** with a full 40-character commit SHA. The workflow now:

1. validates the requested SHA before checkout and confirms the exact checkout;
2. builds and pushes the immutable candidate with BuildKit `provenance=mode=max` and SBOM enabled;
3. installs Trivy 0.74.0 from a SHA-256-pinned official release;
4. fails on HIGH or CRITICAL image findings;
5. generates a CycloneDX image SBOM;
6. issues provenance and SBOM attestations against the image digest;
7. verifies both predicate types using the pinned GitHub CLI;
8. binds the four evidence-file digests into the immutable image manifest.

Do not use `load:true`, rebuild after scanning, promote a tag without its digest, or pass secrets as
build arguments.

## 6. PATH-3 live verification

Dispatch **PATH-3 Runtime Verification** with:

- `environment_id=staging-pg16`
- `image_build_run_id=<successful Runtime Image Provenance run ID>`
- `allow_partial=false`
- `keep_stack=false`

PATH-3 independently downloads the manifest and verifies both:

- `https://slsa.dev/provenance/v1`
- `https://cyclonedx.org/bom`

It then rejects missing/invalid scan, SBOM, provenance-verification, or SBOM-verification digests,
pulls images by digest, and executes the live PostgreSQL/runtime probes on the protected runner.

## 7. Promotion boundary

Only after PATH-3 succeeds, dispatch **Runtime Verification Promotion**. Its protected
`runtime-verification-approval` environment must have independent required reviewers and branch
restrictions. The promotion applies `runtime_verified` only through a reviewable PR; it must never
set `production_certified=true`.

## 8. Failure and rollback

- Trivy database unavailable: fail; do not translate missing data into zero vulnerabilities.
- Attestation or SBOM predicate missing: fail; do not use tag presence as provenance.
- Ruleset evidence unreadable or CODEOWNER review disabled: GATE-01 remains closed.
- PostgreSQL/live runner unavailable: retain `runtime_verified=false`.
- Revoked, expired, consumed, wrong-SHA, or wrong-byte adjudication: reject and issue a new one.
- A bad policy/workflow change is reverted through a normal reviewed PR; do not weaken the guard or
  add a bypass actor to restore throughput.

## Environment limitation

The restricted local environment cannot run Docker/BuildKit or PostgreSQL under a mapped non-root
UID. Disabling seccomp/AppArmor or using BuildKit `--oci-worker-no-process-sandbox` is not an
approved workaround. Image and PostgreSQL evidence must come from the trusted runner described
above.
