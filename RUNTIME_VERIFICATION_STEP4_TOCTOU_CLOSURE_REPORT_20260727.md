# SAHOOL — Step-4 TOCTOU and Promotion Authority Closure

Date: 2026-07-27

## Scope

This patch closes the forensic findings against the governed Step-4 PR foundation while preserving zero-state and PR-only mutation.

## Enforced controls

- Application checkout must equal the exact PATH-3 tested target SHA; promotion onto a descendant is rejected.
- Candidate binds and apply revalidates the capability registry, identity map, runtime bridge, trusted-environment registry, aggregate functional-probe plans, apply tool, PATH-3 workflow, and promotion workflow.
- Capability `status` taxonomy is preserved; only `runtime_verified` may change from false to true.
- Candidate and approval attestation verification outputs and their SHA-256 digests are retained in the committed application ledger.
- The approval environment is certified fail-closed through the GitHub Environments API for required reviewers and deployment/branch restrictions.
- Candidate TTL defaults to 240 minutes; expiry remains strict and cannot be renewed without a fresh PATH-3 candidate.
- Existing ledger records and existing open or merged promotion PRs are checked before application.
- `production_certified` remains false and cannot be changed by this workflow.

## Honest runtime state

No PATH-3 live candidate, approval, application, or promotion PR was produced in this offline environment.

- runtime_verified changes: 0
- production_certified changes: 0
- direct default-branch writer: absent
