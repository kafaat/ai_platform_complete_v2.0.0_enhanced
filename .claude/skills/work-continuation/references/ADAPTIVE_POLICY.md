# Adaptive policy: decisions, not hard-coded assumptions

## Detect task and capabilities

Work types: `creative`, `research`, `document`, `code`, `operations`, `mixed`. This is a description, not a gate; more than one can apply.

Before selecting a procedure, discover whether each capability is `available`, `unavailable`, `unknown`, or `not_applicable`:
- Read current inputs and primary evidence (files, connected services, user-provided content).
- Compute content fingerprints, access current version metadata, write local checkpoints.
- Execute commands and tests, use version-control metadata, schedule/delegate work.
- Read/write a persistent remote store, coordinate shared resources, read back external effects.

Do **not** claim a filesystem or Git simply because the agent is Codex/Claude/Kimi. Do **not** infer persistence merely because state appears in a container. For unknown capability, attempt a safe read-only probe when permitted, or explicitly mark unverified.

## Select overhead by expected failure cost

- `LIGHT`: small isolated request, no need for durable state; deliver result directly and cite any sources. No mandatory state files.
- `CHECKPOINTED`: long run, expensive repeat work, more than one session, or costly interruption; create small, verified checkpoints at **meaningful completion boundaries**.
- `COORDINATED`: multiple agents, shared mutable state, external effects, regulated or high-stakes action; require target-specific authorization, idempotency and concurrency plan.

A task lasting 15 minutes can be COORDINATED; a one-hour literature summary may be CHECKPOINTED without any Git.

## Dynamic procedure lookup

| Scenario | Optional procedure | Never infer |
|---|---|---|
| Software code | branch/tree checks and scoped tests | code changes imply deployment permission |
| Long test suite | shard manifest and exit-code receipts | shard pass means one contiguous run |
| Research | source URLs, publication/observation dates, freshness window | a page remains current indefinitely |
| Docs/spreadsheets/slides | source version, revision fingerprint, change log | document is a Git commit |
| Creative project | deliverable versions, approvals/constraints, preview evidence | arbitrary test commands are needed |
| External action | permission receipt, operation ID, target confirmation | timeout means failure |
| Multi-agent | source ownership, real shared lock when available | process PID means lock holder exists elsewhere |

If no tools can persist data, keep the best verified summary in the answer. Ask for a durable store only when one is necessary and can actually be connected by the user; do not promise persistence across chats.
