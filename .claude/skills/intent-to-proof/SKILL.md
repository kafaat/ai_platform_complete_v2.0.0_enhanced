---
name: intent-to-proof
description: "Turns a goal into requirements, tasks and acceptance evidence before work starts. Use for multi-step work without acceptance criteria, or when scope changes. Not for one-step edits."
metadata:
  version: "4.2.0"
  package: uwrp-professional
---
# Intent → proof

**Use when** multi-step work has no acceptance criteria, or the scope changes mid-work. **Skip** for one-step edits and plain questions.

1. **Capture** the goal, audience, exclusions, constraints, current state, authority, risks and deliverables. Keep the contract minimal.
2. **Define proof first.** Every requirement gets an observable acceptance condition and an evidence type (test, trace, source, document review, receipt). `NOT_RUN`, `SKIPPED` and `PASS` are different results.
3. **Decompose** into small tasks with `id`, `depends_on`, `owner`, the requirement ids they serve and the artifact they produce. One writer per shared mutable resource.
4. **Check the contract, measure it:**
   `python3 scripts/check_contract.py <contract.json>`
   It rejects `VERIFIED` without evidence, `PASS` evidence without an exit code or reference, tasks pointing at unknown requirements, dependency cycles and two writers on one resource, and it reports **evidence closure** (verified requirements ÷ all). Add `--require-closure 1.0` to use it as a completion gate. Start from [`assets/work-contract.example.json`](assets/work-contract.example.json).
5. **Execute and converge.** When evidence changes the specification, update the contract and record the decision ([`assets/decision-record.example.json`](assets/decision-record.example.json)); recheck only invalidated work. Never rewrite acceptance after the fact to fit a failed result.
6. **Report** each requirement as `VERIFIED`, `PARTIAL`, `BLOCKED` or `UNKNOWN` with its reason, plus the closure figure. Claim acceptance only for the agreed scope and the exact versions tested; focused local tests are not release certification.

Patterns adapted (not copied) from GitHub Spec Kit and OpenSpec; no external CLI required.

**Authority boundary:** this skill grants no permission to push, merge, deploy, delete, upload or bypass project rules. The user's instructions and project policy win.
