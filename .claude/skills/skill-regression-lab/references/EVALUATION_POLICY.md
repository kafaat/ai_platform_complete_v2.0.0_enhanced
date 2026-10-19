# Skill evaluation and trust boundaries

Compare **same task IDs**, input digests, agent/model/tool environment, rubrics, run counts and case weighting. Quality gains on an easier dataset are not evidence of improvement.

## Levels (not interchangeable)

1. `STATIC_VALIDATED`: frontmatter, references, checksums and code-contract tests.
2. `TRIGGER_EVALUATED`: blind choice of skills vs no-skill negatives.
3. `REPORTED_BEHAVIOR_COMPARISON`: users provided A/B scores; report checks arithmetic and completeness. Grading authenticity is not independently verified.
4. `INDEPENDENTLY_REVIEWED`: reviewer audits original task outputs, traces, scores, safety and confounders.
5. `PILOT_ACCEPTED`: authorized owner accepts reversible pilot and rollback.
6. `OPERATIONAL_APPROVED`: separately authorized after project-specific gates.

The bundled tool only computes **level 3 conditional statistics**; for synthetic input it produces `SANDBOX_ONLY`. Reported real data can yield `REPORTED_REVIEW_CANDIDATE`, **never** `OPERATIONAL_APPROVED`.

Default policy: minimum 3 cases with >=2 repetitions per arm; each case weighted equally, independent of repetitions; no safety violation, no case regression beyond configured threshold, no unacceptable cost increase, mean quality gain >= configured floor. All these are configurable and need domain-specific justification. Consider uncertainty across seeds/models and holdout tasks before operational promotion.

Security: never execute unknown code or remote shell from a skill. Deny high-risk permissions until separately authorized. Keep raw eval traces private; use digests and scrubbed evidence references in shared summaries.
