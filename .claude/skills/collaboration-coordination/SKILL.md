---
name: collaboration-coordination
description: "Prevents conflicting work across agents, branches or sessions: one writer per resource, verified handoff, no lock release by age. Use when several agents share files, locks or tasks."
metadata:
  version: "4.2.0"
  package: uwrp-professional
---
# Multi-agent ownership

**Use when** several agents, CI jobs, branches or sessions may touch the same files, state, accounts or services. **Skip** for single-agent work on resources nobody else writes.

1. Before assigning, inspect current branches, PRs, tasks and shared resources. Split only truly independent work; name one writer-of-record per resource and read-only reviewers.
2. Give each assignment a `work_id`, `resource_scope`, owner, base version, required receipts and escalation path ([`assets/agent-assignment.example.json`](assets/agent-assignment.example.json)). Never give one mutable file, environment or database to two writers.
3. Prefer an atomic reservation from the shared backend ([`assets/coordination-reservation.example.json`](assets/coordination-reservation.example.json)). A git ref created without force can reserve a name, but it **is not a complete lease/fencing system** and cannot stop a stale writer.
4. For durable writes use compare-and-swap or conditioned writes, and fencing tokens checked by the resource where supported. With no shared coordination, serialize; do not write concurrently.
5. Never release a lock because of its **age or an old PID alone**. Prove the holder is inactive from current authoritative state; an invisible cloud session is `UNKNOWN`.
6. Reviews are separate tasks with their own evidence. Several AI reviews are not independent human acceptance.
7. Hand over ownership only with versions, receipts, open conflicts and the new owner's acknowledgement. A timed-out side effect needs a target-state lookup first.

A local `flock`, GitHub `concurrency` and GitLab `resource_group` each cover only their own scope; none is a global lock.

**Authority boundary:** this skill grants no permission to push, merge, deploy, delete, upload or bypass project rules. The user's instructions and project policy win.
