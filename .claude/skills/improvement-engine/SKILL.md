---
name: improvement-engine
description: "Use when recurring documented experiences suggest changing a skill or workflow. Draft evidence-linked proposals only; never edit, approve or publish rules automatically."
metadata:
  version: "4.3.0"
  package: uwrp-professional
---
# Improvement Engine — hypothesis, not automatic promotion

Convert repeated observations into a **candidate change proposal** without rewriting trusted rules or hiding prior failures.

1. Read a validated experience journal or separately verified evidence set. Current journal events are always `RECORDED_UNVERIFIED`: integrity is **not** the truth of the claim.
2. Require at least two **distinct evidence digests** for the same skill and signal before drafting a pattern-level suggestion. The number of observations alone is not independence.
3. Analyze root cause, counterexamples and alternative explanations. If evidence conflicts or is unavailable, keep `INSUFFICIENT_EVIDENCE` and record the missing proof.
4. Draft a minimal, reversible candidate specifying skill name, version, previous digest, proposed diff, expected improvement, potential harms, regression suite and rollback. Do not make the diff yourself without separate user authority and project gates.
5. Route a candidate to independent evaluation (`skill-regression-lab` when available, or equivalent) and review; never self-approve, auto-publish, or change authorization language.
6. Track the outcome including rejected or negative results. Avoid training on one off outlier or agent-generated unverified assertions.

**Optional read-only derivation:** `python3 scripts/draft_proposals.py --journal /authorized/scratch/experiences.jsonl` prints suggestions. The `--out` option writes a draft only at an explicitly selected local destination, not to any skill file.

See [Proposal contract](references/PROPOSAL_POLICY.md) and [proposal template](assets/proposal.example.json). This Skill does not grant permissions for Git operations or deployment.
