# Problem → capability → proof (design matrix)

| Observed failure mode | Skill or mechanism | Required proof | Not a proof |
|---|---|---|---|
| Restart loses state | UWRP checkpoint & handoff | Read-back verified state at expected input version | Chat transcript claim |
| Slow tests rerun after interruption | Adaptive Test Accelerator | Per-shard receipts + count/skip/inventory and context | Combined shard results described as continuous preflight |
| Work begins with vague objective | intent-to-proof | Requirement→task→artifact→acceptance trace | Elaborate plan without falsifiable conditions |
| Unreliable internet/source assertions | evidence-research | Upstream link/version, comparison and confidence | Several mirrors of same repository |
| Fix without identifying cause | failure-investigation | Negative witness before, positive witness after | Green unrelated tests |
| Multiple agents edit same resource | collaboration-coordination | Exclusive writer and verified transfer/lock | Stale local PID or uncoordinated chat agreement |
| PR looks clean but base moved | change-review + UWRP validity | Fresh base/merge-base, gate receipts tied to head | Prior green CI |
| Push/merge/deploy uncertain after timeout | safe-delivery | Target-state evidence with stable action ID | Timeout interpreted as failure |
| Skills trigger needlessly or bypass rules | skill-evaluator | Positive/negative trigger and with/without comparisons | YAML frontmatter valid only |
| Source archives tampered/mirror ambiguity | pack validator + supply chain practice | SHA + upstream provenance and license | Hash alone authenticates author |
