# Controlled improvement lifecycle

`OBSERVED → PATTERN_CANDIDATE → DRAFT → EXPERIMENTAL → INDEPENDENT_REVIEW → OWNER_APPROVAL → PILOT → RELEASE`.

- Every progression requires explicit evidence and responsible authority. Steps do **not** occur automatically because a local validator returns 0.
- Pin original Skill SHA-256, candidate SHA-256, dataset revision, model/tool context and grading rubric before comparison. The baseline must remain retrievable for rollback.
- Minimize change scope. A success means reproducing the failure before change and eliminating it afterwards **without** introducing safety or authority regressions.
- Never modify governance, permissions, secret-handling rules, or required acceptance gates solely because a model proposes it.
- Suggestions based only on a hash-chained journal still require primary evidence examination: collision-resistant hashing does not prove source authenticity.
- A single failure can justify an urgent *manual* safety investigation; the two-evidence threshold limits automatic pattern classification, not human incident response.
