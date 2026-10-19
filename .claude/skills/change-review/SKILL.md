---
name: change-review
description: "Independent review of a proposed change against its exact diff, base, tests and gates. Use before accepting or merging code, docs or config. Not for writing the change itself."
metadata:
  version: "4.2.0"
  package: uwrp-professional
---
# Independent change review

**Use when** a proposed change to code, docs, config or workflow must be accepted, rejected or merged. **Skip** while writing the change; review comes after.

1. **Pin the version:** exact head, base and merge-base, scope and governing policies. Refresh branch and PR state; it is volatile.
2. **Review independently.** The reviewer works from the diff, the contract and the gates, not from the author's reasoning. In an agent that supports sub-agents, run the review in a fresh context given only those three; record who reviewed ([`assets/review-decision.example.json`](assets/review-decision.example.json)).
3. Read the **actual diff or artifact**, never only its description. Weigh correctness, compatibility, security, tenant and privacy boundaries, failure modes, migrations and rollback in proportion to risk.
4. Each finding carries severity, location, failing scenario, observed-or-inferred evidence, the invariant at stake, and a repair criterion; classify as `BLOCKER`, `RECOMMENDATION` or `UNKNOWN` ([`assets/risk-review.example.json`](assets/risk-review.example.json)).
5. Look for a **negative control** that would expose a false PASS. Confirm the tests ran on the proposed final version. If the base moved since testing, base-sensitive results are invalid even when the feature tree is unchanged.
6. Verdict: `PASS`, `PASS_WITH_LIMITS`, `CHANGES_REQUIRED` or `EVIDENCE_MISSING`, plus the next verified step. An automated reviewer may recommend; it never stands in for a required human approval, and it does not replace project gates.

No endorsement from test counts, description-only reviews or another agent's assertion.

**Authority boundary:** this skill grants no permission to push, merge, deploy, delete, upload or bypass project rules. The user's instructions and project policy win.
