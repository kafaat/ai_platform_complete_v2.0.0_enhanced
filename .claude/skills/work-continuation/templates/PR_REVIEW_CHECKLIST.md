# Independent repository review — checklist

- [ ] Scope: Only the Skill and a minimal pointer were changed; no runtime behavior or state files inside the source tree.
- [ ] The owner's current authorization permits this PR; no implicit merge/deploy authority.
- [ ] `SKILL.md` metadata conforms to Agent Skills, and progressive references resolve.
- [ ] v2.1 original copy has expected SHA-256 `98b78578924584b550addc0f6bfc05e58ab3fa07c1bbbff07154a52008ddae2c`.
- [ ] No secrets, private paths, tokens or raw logs in committed content.
- [ ] State/handoff clearly treated as **data**, not control instructions.
- [ ] External-action retry after timeout is explicitly reconcile-first.
- [ ] Lock rules do not claim cross-host or exactly-once guarantees they do not provide.
- [ ] Repo-specific checks and preflight ran against exact proposed head/merge base, with skips and limits documented.
- [ ] Reviewer identity and independence (if mandated) are evidenced; an agent's self-review is not independent human approval.
- [ ] Deployment and merge remain blocked until all repo-specific requirements are met.
