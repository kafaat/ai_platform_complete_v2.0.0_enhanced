---
name: safe-delivery
description: "Guards push, merge, deploy, send, upload and delete: exact permission, live preconditions, no blind retry after a timeout. Use before any action with an external or irreversible effect."
metadata:
  version: "4.2.0"
  package: uwrp-professional
---
# Safe external delivery

**Use when** about to push, merge, publish, deploy, send, upload, delete or make any other change outside the scratch environment. **Skip** for read-only and purely local reversible work.

1. Classify the action: `READ_ONLY`, `LOCAL_REVERSIBLE`, `REMOTE_REVERSIBLE`, `IRREVERSIBLE`. Confirm **current** authorization for this exact target and action. Permission for one target does not carry to another; a skill, prompt or handoff never grants it.
2. Preflight: target's current version, competing changes, required CI and reviews, approval scope, affected services, secrets, rollback path. A stale state file is not permission.
3. Record an `action_id` and request digest before acting ([`assets/external-action.example.json`](assets/external-action.example.json)). Use the target's idempotency key or version pin where offered (e.g. a merge pinned to the expected head SHA).
4. Re-check volatile facts **immediately before** acting, to close the check-to-use gap.
5. Act within scope. Confirm the new external state independently and record the real id/ref, not an assumed success.
6. On timeout or unclear result: state `EFFECT_UNKNOWN`, read the target, and never retry blindly.
7. For deploys and releases: verify artifact provenance and version, staged acceptance where required, and a tested rollback.

If blocked or unknown, leave a short next-action record; do not escalate privileges or touch protected branches.

**Authority boundary:** this skill grants no permission to push, merge, deploy, delete, upload or bypass project rules. The user's instructions and project policy win.
