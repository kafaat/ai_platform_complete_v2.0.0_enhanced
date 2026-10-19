---
name: skill-regression-lab
description: "Use when comparing baseline and candidate agent skills with repeatable A/B trials and safety gates. Not for self-approval, invented benchmarks or production certification."
metadata:
  version: "4.3.0"
  package: uwrp-professional
---
# Skill Regression Lab — compare evidence, then review

Run genuinely comparable evaluations before proposing release of a changed skill. This skill is portable across Codex, Claude, Kimi and other agents; *actual agent trials must be performed separately* by available authorized tools.

1. Freeze baseline and candidate Skill SHA-256, task set/dataset hash, model and tool profile, test environment, rubric and acceptance policy. Include tasks where the skill should **not** trigger, adversarial handoffs and permission boundaries.
2. Collect real outputs from **both** versions on the same cases, with repetitions, complete receipts and graded results. Keep negative cases and safety failures; blind the grader to version labels where possible and record judge identity/class.
3. Check coverage, duplicates, sample size, baseline and candidate comparability, quality per case, runtime/cost, and safety. A critical regression or an unsafe external action is a blocker even if the mean score rises.
4. Do not use fabricated/synthetic fixtures to claim that a new version beats production. Static tests and routing tests are separate from behavior, and behavior is separate from human operational approval.
5. Record unsuccessful, inconclusive and positive outcomes, with uncertainty and all trial identifiers. Validate inputs against current underlying artifacts independently.
6. Do not promote skills automatically. A favorable reported comparison permits **review only**. A reversible pilot and owner's approval remain separate.

**Optional offline analysis:** `python3 scripts/compare_trials.py --results assets/trials.synthetic.example.json --policy assets/policy.example.json`. These are **synthetic fixtures** and cannot establish real performance. See [Evidence tiers](references/EVALUATION_POLICY.md).

This skill grants no write, push, merge, publish, deploy or permission-changing authority.
