# SAHOOL Pre-Push Stable-Tree Protocol

This protocol prevents measurements, generated artifacts, or commits from being produced while another process is mutating the worktree.

## Mandatory order

1. Stop all test and generation processes.
2. Run `python scripts/ops/pre_push_stability_guard.py --allow-dirty` before regeneration.
3. Regenerate canonical artifacts exactly once.
4. Write route-source attestations.
5. Build the release bundle last.
6. Validate release checksums.
7. Run `python scripts/ops/pre_push_stability_guard.py` on the clean tree.
8. Stage explicit paths or the reviewed diff; do not run `git add -A` while jobs are active.
9. Run the final suites once on the undisturbed staged/committed tree.
10. Push.

CI may run the contamination/stability portion with:

```bash
python scripts/ops/pre_push_stability_guard.py --skip-process-check --allow-dirty
```

The guard rejects temporary route probes, Python bytecode/cache artifacts, a changing worktree, a dirty tree in final mode, and known concurrent mutators such as pytest, generated sweeps, route writers, and release builders.
